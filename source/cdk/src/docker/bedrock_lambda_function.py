import boto3
import json
from boto3.dynamodb.conditions import Key
from langchain_aws import ChatBedrock
from langchain_core.messages import (
    HumanMessage,
    AIMessage
)
# from langchain_community.embeddings.bedrock import BedrockEmbeddings
# from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain_community.document_loaders.merge import MergedDataLoader
# from langchain_community.document_loaders.csv_loader import CSVLoader
# from langchain_community.document_loaders import TextLoader
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.prompts.chat import ChatPromptTemplate
from langchain.chains import create_history_aware_retriever
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.retrieval import create_retrieval_chain
import os
import time
import qnaUtils as qna
import utils
from dynamodb_retriever import DynamoDBRetriever as ddb


# def cvs_load_data():
#     return CSVLoader(
#         file_path=os.environ.get('CSV_FILE_PATH', "docs/products.csv"),
#         csv_args={
#             'delimiter': ',',
#             'quotechar': '"'#,
#             #'fieldnames': ['Index', 'Height', 'Weight']
#         }
#     )

# def instructions_load_data():
#     return TextLoader(
#         file_path=os.environ.get('INSTRUCTIONS_FILE_PATH', "docs/instructions.txt"),
#     )

# def merge_data_loaders():
#     loaders=[
#         cvs_load_data(), 
#         instructions_load_data()]
#     loaders_all = MergedDataLoader(loaders=loaders)
#     docs_all = loaders_all.load()
#     text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
#     splits = text_splitter.split_documents(docs_all)
#     vectorstore = Chroma.from_documents(documents=splits, embedding=BedrockEmbeddings(model_id="amazon.titan-embed-text-v2:0"))
#     return vectorstore.as_retriever()

table_config = None

def history_aware_retriever(llm, table_config, group_id):
    #retriever = merge_data_loaders()
    print("table_config:", table_config)
    retriever = ddb(target_table=table_config, group_id=group_id)
    contextualize_q_system_prompt = qna.contextualize_q_system_prompt
    # print(contextualize_q_system_prompt)
    contextualize_q_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", contextualize_q_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    return create_history_aware_retriever(
        llm, retriever, contextualize_q_prompt
    )

def create_aware_chain(llm, table_config, group_id):
    # load the qa_system_prompt from the qaUtils.py
    qa_system_prompt = qna.qa_system_prompt
    # print(qa_system_prompt)
    qa_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", qa_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )

    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)

    return create_retrieval_chain(history_aware_retriever(llm, table_config, group_id), question_answer_chain)

# def format_docs(docs):
#     return "\n".join(d.page_content for d in docs)

def get_history(session_id):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ.get("DYNAMO_TABLE", "aibot_conversation_history"))
    response = table.query(
        KeyConditionExpression=Key('session_id').eq(session_id)
    )
    return response
# Document what this function does its imputs and possible responses

def get_conversation_history(session_id):
    # Implement logic to retrieve conversation history from a database or cache
    # based on the session_id
    history = get_history(session_id)
    history = history.get('Items', [])
    messages = []
    #valid_history = 0
    if history:
        for item in history:
            if item['sender'] == 'user':
                #valid_history += 1
                messages.append(HumanMessage(content=item['message']))
            else:
                #valid_history -= 1
                messages.append(AIMessage(content=item['message']))
            #if valid_history < 0:
                ## user conversation is not stored correctly 
                # TODO delete items to prevent further user bad experience
            #    return []
    return messages

def store_item(session_id, item, role):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ.get("DYNAMO_TABLE", "aibot_conversation_history"))
    timestamp = time.time()
    timestamp_str = f"{int(timestamp)}.{int(timestamp * 1000000) % 1000000}"
    # create a timestamp named expiration_time for the dynamo ttl for 2 weeks
    expiration_time = int(timestamp + 1209600)  
    #create query item
    item = {
        'session_id': session_id,
        'timestamp': timestamp_str,
        'expiration_time': expiration_time,
        'sender': role,
        'message': item
    }
    table.put_item(Item=item)
    return

def get_response(query, session_id, table_config, group_id = "default"):
    llm = ChatBedrock(model_id=os.environ.get("MODEL_ID","anthropic.claude-instant-v1"),
                      model_kwargs={"temperature": os.environ.get("TEMPERATURE", 0.3)})
    chat_history = get_conversation_history(session_id)
    rag_chain = create_aware_chain(llm, table_config, group_id)
    #print(rag_chain.get_verbose())
    response = rag_chain.invoke({"input": query, "chat_history": chat_history})
    store_item(session_id, query, "user")
    store_item(session_id, response["answer"], "ai")
    return response

def lex_response_builder(session_id, llm_result, intent_fulfilled=False):
    response = {
        "sessionState": {
            "dialogAction": {
                "type": "Close" if intent_fulfilled else "ElicitIntent"
            }
        },
        "messages": [
            {
                "contentType": "PlainText",
                "content": llm_result
            }
        ]
    }
    return response

def lambda_handler(event, context):
    print("event:", event)
    session_id = event.get("sessionId", None)
    query = event.get("inputTranscript",None)
    if session_id is None:
        body = json.loads(event['body'])
        config = body.get("config", None)
        table = "DYNAMO_TABLE_LLM" if config == "llm" else "DYNAMO_TABLE_TEXTRACT"
        table_config = table
        session_id = str(body.get("sessionId", None))
        query = body.get("inputTranscript",None)
        cognito_groups = event["requestContext"]["authorizer"]["claims"]["cognito:groups"]
        response = get_response(query, session_id, table_config, cognito_groups)
        return utils.response(json.dumps(response["answer"]))
    else:
        config = event.get("config", None)
        table = "DYNAMO_TABLE_LLM" if config == "llm" else "DYNAMO_TABLE_TEXTRACT"
        table_config = table
        cognito_groups = "default"
        response = get_response(query, str(session_id), table_config, cognito_groups)
        # print("response:", response)
        lex_response = lex_response_builder(session_id, response["answer"])
        # print("response:", lex_response)
        return lex_response
