# a lambda function that receives a file name and returns a signed url from s3 to upload the file
import boto3
import os
import json
import utils
from botocore.config import Config

config = Config(signature_version='s3v4', s3={"addressing_style": "virtual"})
s3 = boto3.client('s3', config=config)


def handler(event, context):
    #check if the event comes with a cognito group
    try:
        # get the user groups from cognito in the event
        groups = event['requestContext']['authorizer']['claims']['cognito:groups'].split(',')
    except KeyError:
        return utils.response(json.dumps({'error': 'Contact Your administrator: CognitoGroupNotFound, ensure that your user is assigned to a cognito group'}), code=400)
    ## TODO let the user decide for what group they want to upload he document if in multiple groups
    ## if not in multiple groups, use the first group
    group = groups[0]
    
    #print(event)
    body =  event['queryStringParameters']
    #body = json.loads(body)
    if 'file_name' not in body:
        return utils.response(json.dumps({'error': 'No file name found in the request'}), code=400)
    file_name = body['file_name']
    bucket_name = os.environ.get('BUCKET', None)
    upload_prefix = os.environ.get('UPLOAD_PREFIX', "")
    object_key = f'{upload_prefix}{group}/{file_name}'
    presigned_url = s3.generate_presigned_url(ClientMethod='put_object', Params={'Bucket': bucket_name, 'Key': object_key}, ExpiresIn=3600)
    return utils.response(json.dumps({'url': presigned_url}))