import os
headers = {
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Origin': os.environ['CORS_ORIGIN'] if 'CORS_ORIGIN' in os.environ else '*',
    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
}
def response(body, code = 200,):
    return {
        'statusCode': code,
        'headers': headers,
        'body': body
    }