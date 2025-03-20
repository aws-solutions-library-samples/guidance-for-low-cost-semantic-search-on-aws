## a lambda handler that gets executed with a UserPool POST_CONFIRMATION that adds the confirmed user to a "default" cognito group
import boto3
import json

client = boto3.client('cognito-idp')

def handler(event, context):
    print("event:", event)
    response = client.admin_add_user_to_group(
        UserPoolId=event['userPoolId'],
        Username=event['userName'],
        GroupName='default'
    )
    return event