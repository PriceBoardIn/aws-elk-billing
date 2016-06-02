import boto3
import time
import socket
import sys
import datetime
from dateutil.relativedelta import relativedelta
import subprocess
import os

'''
Todo:
Error Handling
User Interface
'''


elasticsearch_socket	= socket.socket()
logstash_socket			= socket.socket()
kibana_socket			= socket.socket()

for _ in range(15):
	try:
		print 'Checking if Elasticsearch container has started to listen to 9200'
		elasticsearch_socket.connect(('elasticsearch', 9200))
		print 'Great Elasticsearch is listening on 9200, 9300 :)'
		break
	except Exception as e:
		print("Something's wrong with Elasticsearch. Exception is %s" % (e))
		print 'I will retry after 4 seconds'
		time.sleep(4)

for _ in range(15):
	try:
		print 'Checking if Logstash container has started to listen to 5140'
		logstash_socket.connect(('logstash', 5140))
		print 'Great Logstash is listening on 5140 :)'
		break
	except Exception as e:
		print("Something's wrong with Logstash. Exception is %s" % (e))
		print 'I will retry after 4 seconds'
		time.sleep(4)

for _ in range(15):
	try:
		print 'Checking if Kibana container has started to listen to 5160'
		kibana_socket.connect(('kibana', 5601))
		print 'Great Kibana is listening on 5601 :)'
		break
	except Exception as e:
		print("Something's wrong with Kibana. Exception is %s" % (e))
		print 'I will retry after 4 seconds'
		time.sleep(4)

elasticsearch_socket.close()
logstash_socket.close()
kibana_socket.close()

# you must provide your credentials in the recomanded way, here we are passing it by ENV variables
s3 = boto3.client('s3')

# give the correct bucket name for your s3 billing bucket
bucketname = os.environ['S3_BUCKET_NAME'] 
path_name_s3_billing = os.environ['S3_BILL_PATH_NAME']
#timestamp
timestamp = time.strftime('%H_%M')

# generate the aws s3 directory format for getting the correct json file
generate_monthly_dir_name = datetime.date.today().strftime('%Y%m01')+'-'+\
                        (datetime.date.today()+relativedelta(months=1)).strftime('%Y%m01')

# json file name
latest_json_file_name = path_name_s3_billing+'/'+generate_monthly_dir_name\
                +path_name_s3_billing+'-Manifest.json'

# delete previous getfile and  csv files and part downloading files
process_delete_csv = subprocess.Popen(["find -name 'billing_report_*' -exec rm -f {} \;"],shell=True)
process_delete_json = subprocess.Popen(["find -name 'getfile*' -exec rm -f {} \;"],shell=True)

# download the jsonfile as getfile_$time.json from s3
s3.download_file(bucketname,latest_json_file_name,'getfile'+timestamp+'.json')

# read the json file to get the latest updated version of csv
f = open('getfile'+timestamp+'.json','r')
content=eval(f.read())
latest_gzip_filename = content['reportKeys'][0]
f.close()

# the local filename formated for compatibility with the go lang code
local_gz_filename = 'billing_report_'+timestamp+'_'+datetime.date.today().strftime('%Y-%m')+'.csv.gz'
local_csv_filename = local_gz_filename[:-3]

# downloading the zipfile from s3
s3.download_file(bucketname,latest_gzip_filename,local_gz_filename)

#upzip and replace the .gz file with .csv file
print("Extracting latest csv file")
process_gunzip = subprocess.Popen(['gunzip -v '+ local_gz_filename],shell=True)

#current month index format (name)
index_format = datetime.date.today().strftime('%Y.%m')

#DELETE earlier aws-billing* index if exists
status = subprocess.Popen(['curl -XDELETE elasticsearch:9200/aws-billing-'+index_format], shell=True)
if status.wait() != 0:
    print 'I think there are no aws-billing* indice or it is outdated, its OK main golang code will create a new one for you :)'
else:
    print 'aws-billing* indice deleted, its OK main golang code will create a new one for you :)'

#Index aws mapping json file
status = subprocess.Popen(['curl -XPUT elasticsearch:9200/_template/aws_billing -d "`cat /aws-elk-billing/aws-billing-es-template.json`"'], shell=True)
if status.wait() != 0:
    print 'Something went wrong while creating mapping index'
    sys.exit(1)
else:
    print 'ES mapping created :)'

#Index Kibana dashboard
status = subprocess.Popen(['(cd /aws-elk-billing/kibana; bash orchestrate_dashboard.sh)'], shell=True)
if status.wait() != 0:
    print 'Kibana dashboard failed to indexed to .kibana index in Elasticsearch'
    sys.exit(1)
else:
    print 'Kibana dashboard sucessfully indexed to .kibana index in Elasticsearch :)'

#Index Kibana visualization
status = subprocess.Popen(['(cd /aws-elk-billing/kibana; bash orchestrate_visualisation.sh)'], shell=True)
if status.wait() != 0:
    print 'Kibana visualization failed to indexed to .kibana index in Elasticsearch'
    sys.exit(1)
else:
    print 'Kibana visualization sucessfully indexed to .kibana index in Elasticsearch :)'

#Run the main golang code to parse the billing file and send it to Elasticsearch over Logstash
status = subprocess.Popen(['go run /aws-elk-billing/main.go --file /aws-elk-billing/'+local_csv_filename], shell=True)
if status.wait() != 0:
    print 'Something went wrong while getting the file reference or while talking with logstash'
    sys.exit(1)
else:
    print 'AWS Billing report sucessfully parsed and indexed in Elasticsearch via Logstash :)'


# /sbin/init is not working so used this loop to keep the docker up, Have to change it!
while(True):
    pass

