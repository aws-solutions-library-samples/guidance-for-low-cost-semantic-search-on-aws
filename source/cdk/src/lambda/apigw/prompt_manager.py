import boto3
import json
import os
import utils

ssm = boto3.client('ssm')

def handler(event, context):

    # if method is post
    if event['httpMethod'] == 'GET':
        body =  event['queryStringParameters']
        promt_to_get = body['prompt']
        # try and catch if does not exist SSM.Client.exceptions.ParameterNotFound
        
        try:
            if promt_to_get == 'context':
                param_name = os.environ.get('PROMT_CONTEXT_SSM', 'promt_context')
            else:
                param_name = os.environ.get('PROMT_SYSTEM_SSM', 'promt_system')
            prompt = ssm.get_parameter(Name=param_name)['Parameter']['Value']
        except ssm.exceptions.ParameterNotFound as e:
            prompt = ''
        return utils.response(json.dumps({'prompt': prompt}))
    elif event['httpMethod'] == 'POST':
        body = json.loads(event['body'])
        promt_system = body.get('system', None)
        promt_context = body.get('context', None)
        if promt_system:
            #update the ssm parameter
            param_name = os.environ.get('PROMT_SYSTEM_SSM', 'promt_system')
            ssm.put_parameter(Name=param_name, Type='String', Tier='Standard', Value=promt_system, Overwrite=True)

        elif promt_context:
            #update the ssm parameter
            param_name = os.environ.get('PROMT_CONTEXT_SSM', 'promt_context')
            ssm.put_parameter(Name=param_name, Type='String', Tier='Standard', Value=promt_context, Overwrite=True)

    return utils.response(json.dumps({'message': 'Prompt updated'}))