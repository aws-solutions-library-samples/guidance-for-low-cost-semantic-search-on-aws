import boto3
import os
import json
import utils


# "STATE_MACHINE_DELETE": 
# "BUCKET_DOCUMENTS": 
# "TABLE_NAME_BIG": 
# "TABLE_NAME_SMALL": 
#load all the environs
TABLE_DOCUMEMNT = os.environ.get('TABLE_NAME_DOCUMENTS', 'ai_bot_document_finder')
STATE_MACHINE_DELETE = os.environ.get('STATE_MACHINE_DELETE', 'state_machine_delete')
BUCKET_DOCUMENTS = os.environ.get('BUCKET_DOCUMENTS', 'ai-bot-document-finder')
TABLE_NAME_BIG = os.environ.get('TABLE_NAME_BIG', 'ai_bot_document_finder_big')
TABLE_NAME_SMALL = os.environ.get('TABLE_NAME_SMALL', 'ai_bot_document_finder_small')


dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table( TABLE_DOCUMEMNT)
sfn = boto3.client('stepfunctions')

def delete(event):
    # start the execution and send the environs as parameters for the execution
    # get the group from cognito and compare it to the group in the event
    user_groups = event['requestContext']['authorizer']['claims']['cognito:groups'].split(',')
    body = json.loads(event['body'])
    group = body.get('group', None)
    filename = body.get('filename', None)
    if group not in user_groups or filename is None:
        return utils.response(json.dumps({'message': 'Unauthorized'}), 401)
    respone = sfn.start_execution(stateMachineArn=STATE_MACHINE_DELETE, input=json.dumps({
        "documentTable": TABLE_DOCUMEMNT,
        "bigTable": TABLE_NAME_BIG,
        "smallTable": TABLE_NAME_SMALL,
        "fileStoreBucketName": BUCKET_DOCUMENTS,
        "group": group,
        "filename": filename
    }))
    return utils.response(json.dumps({
        'message': 'Deleted',
        'executionArn': respone['executionArn']
        }))

def list_documents(event):
    # query the table for all the documents with the primary key of the name of
    groups = event['requestContext']['authorizer']['claims']['cognito:groups'].split(',')
    documents = []
    for group in groups:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('group').eq(group))
        documents.extend(response['Items'])

    return utils.response(json.dumps(documents))


def handler(event, context):
    #check if the event comes with a cognito group
    try:
        # get the user groups from cognito in the event
        groups = event['requestContext']['authorizer']['claims']['cognito:groups'].split(',')
    except KeyError:
        return utils.response(json.dumps({'error': 'Contact Your administrator: CognitoGroupNotFound, ensure that your user is assigned to a cognito group'}), code=400)
    # if method is get list
    if event['httpMethod'] == 'GET':
        return list_documents(event)
    elif event['httpMethod'] == 'DELETE':
        return delete(event)