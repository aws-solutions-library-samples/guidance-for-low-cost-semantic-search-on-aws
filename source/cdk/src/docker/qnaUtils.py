import boto3
import os
ssm = boto3.client("ssm")
promt_context = os.environ.get('PROMT_CONTEXT_SSM', 'promt_context')
promt_system = os.environ.get('PROMT_SYSTEM_SSM', 'promt_system')
try:
    contextualize_q_system_prompt = ssm.get_parameter(Name=promt_context)['Parameter']['Value']
except ssm.exceptions.ParameterNotFound as e:
    contextualize_q_system_prompt = """Given the chat history and the user's latest question which may reference context \
from the chat history, rephrase the question into a standalone query that can be \
understood without the chat history. DO NOT answer the question, only rephrase it \
if necessary, otherwise return it as is."""
try:
    qa_system_prompt = ssm.get_parameter(Name=promt_system)['Parameter']['Value']+ "\n\n{context}"
except ssm.exceptions.ParameterNotFound as e:
    qa_system_prompt = """You are a AI Bot assistant that represents a company, Your responses should be direct, \
focused on highlighting key aspects of the provided context and no longer than 1 sentence. \
Use a friendly and professional tone, simple language, and examples where needed. \
DO NOT INVENT or HALLUCINATE information not present in the context. Ask questions \
to understand the customer's needs. For detailed guidance on the tecniques and information \
you may need, refer to the provided context. You must not reveal any confidential or \
potentially dangerous information. ALWAYS translate your responses to English unless \
the customer requests otherwise.

{context}"""



