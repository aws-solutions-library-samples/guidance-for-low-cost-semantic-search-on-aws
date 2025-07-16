from aws_cdk import (
    Stack,
    cloudformation_include as cfn,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_cloudfront as _cf,
    aws_s3_deployment as s3deploy,
    aws_cloudfront_origins as origins,
    RemovalPolicy,
    aws_lambda as _lambda,
    aws_lambda_python_alpha as python,
    aws_apigateway as apigateway,
    # iam
    aws_iam as iam,
    Duration,
    aws_ssm as ssm,
    aws_ecr as ecr,
    aws_events as events,
    aws_events_targets as targets,
    aws_stepfunctions as sfn,
    CfnParameter,
    aws_cognito as _cognito,
    aws_certificatemanager as acm,
    aws_stepfunctions_tasks as tasks,
    aws_sns as _sns,
    aws_sns_subscriptions as sns_subscriptions,
    aws_kms as kms,
    aws_logs as logs,
    aws_wafv2 as wafv2
)
import aws_cdk as cdk
import json
from constructs import Construct
import os
import re
import hashlib

class ChatbotStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, waf_acl_arn=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.table_conversation = None
        self.table_chunk_small = None
        self.table_chunk_big = None
        self.lex2_role = None
        self.prediction_lambda = None
        self.s3_file_bucket = None
        self.s3_website_bucket = None
        self.cloudfront_website = None
        self.redirect_uri = None
        self.api_back_signed_url = None
        self.api_back_configure = None
        self.api_backend_resource_chat = None
        self.api_gateway = None
        self.state_machine_delete = None
        self.state_machine_llm_parser = None
        self.state_machine_textract = None
        self.user_pool = None
        self.waf_acl_arn = waf_acl_arn
        self.self_signup = self.node.try_get_context("selfSignup")
        self.create_dynamo_tables()
        self.create_s3_bucket()
        self.create_event_rules()
        self.create_sns_textract()
        self.build_functions()
        self.build_del_document_state_machine()
        self.build_parser_document_state_machine()
        self.create_state_machine()
        self.build_sns_function()
        self.build_query_lambda_func()
        self.create_api_lambdas()
        self.create_user_pool()
        self.build_post_confirmation_trigger()
        self.create_waf()
        self.create_web_app()
        self.create_api_gw()
        self.create_s3_deployment()
        self.outputs()

    def outputs(self):
        admin_portal = "https://"+self.cloudfront_website.distribution_domain_name
        cdk.CfnOutput(self, "AdminPortal", value=admin_portal, description="Admin Portal")

    def create_waf(self):
        # WAF is created in a separate stack in us-east-1
        # The WAF ARN is passed to this stack as a parameter
        pass

    def create_s3_deployment(self):
        s3deploy.BucketDeployment(self, "DeployWebsite",
            sources=[
                s3deploy.Source.asset("./src/web/"),
                s3deploy.Source.json_data("config.json", {
                    "apiendpointupload": self.api_gateway.url + self.api_backend_resource_presing.path[1:],
                    "apiendpointconfig": self.api_gateway.url + self.api_backend_resource_config.path[1:],
                    "apiendpointchat": self.api_gateway.url + self.api_backend_resource_chat.path[1:],
                    "apiendpointdocuments": self.api_gateway.url + self.api_backend_resource_documents.path[1:],
                    "signinurl": self.sign_in_url,
                    "cognitoclientid" : self.client.user_pool_client_id,
                    "cognitoregion" : self.region
                })
            ],
            destination_bucket=self.s3_website_bucket
        )

    def build_post_confirmation_trigger(self):
        self.post_confirmation_trigger = python.PythonFunction(self, "PostConfirmationTrigger",
            entry="src/lambda/cognito",
            index="post_confirmation.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={},
            timeout=Duration.seconds(60),
            memory_size=1024,
        )
        self.post_confirmation_trigger.role.attach_inline_policy(
            iam.Policy(self, "PassRoleToCognitoLambda",
                statements=[
                    iam.PolicyStatement(
                        actions=["cognito-idp:AdminAddUserToGroup"],
                        resources=[self.user_pool.user_pool_arn]
                    )])
        )
        self.user_pool.add_trigger(
            _cognito.UserPoolOperation.POST_CONFIRMATION,
            self.post_confirmation_trigger
        )

    def build_sns_function(self):
        self.step2sns = python.PythonFunction(self, "SNSProcess",
            entry="src/lambda/step2sns",
            index="sns.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                "DOCUMENTS_BUCKET_NAME": self.s3_file_bucket.bucket_name,
                "DOCUMENTS_TABLE_NAME": self.table_documents.table_name,
                "SATE_MACHINE": self.state_machine_textract.state_machine_arn
                },
            timeout=Duration.seconds(900),
            memory_size=1024,
        )
        self.step2sns.add_to_role_policy(
            iam.PolicyStatement(
                actions=["textract:GetDocumentTextDetection"],
                resources=["*"]
            ))
        self.step2sns.grant_invoke(iam.ServicePrincipal("sns.amazonaws.com"))
        self.step2sns.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:PutObjectAcl", "s3:PutObjectTagging", "s3:PutObjectVersionAcl"],
                resources=[self.s3_file_bucket.bucket_arn + "/*"]
            )
        )
        self.step2sns.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:GetItem"],
                resources=[self.table_documents.table_arn]
            )
        )
        self.step2sns.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[self.state_machine_textract.state_machine_arn]
            )
        )
        _sns.Subscription(
            self, "TextractSubscription",
            topic=self.sns_topic,
            endpoint=self.step2sns.function_arn,
            protocol=_sns.SubscriptionProtocol.LAMBDA
        )

    def create_sns_textract(self):
        # KMS key 
        sns_alias = kms.Alias.from_alias_name(self, "sns_key_alias", "alias/aws/sns")
        # Create an SNS topic
        self.sns_topic = _sns.Topic(
            self, "TextractTopic",
            display_name="Textract Topic",
            topic_name="AmazonTextract",
            master_key=sns_alias
        )
        # role for textract to publish to sns
        self.sns_role = iam.Role(
            self, "TextractRole",
            assumed_by=iam.ServicePrincipal("textract.amazonaws.com"),
            description="Role for Textract to publish to SNS"
        )
        # get the AmazonTextractServiceRole
        self.sns_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=[self.sns_topic.topic_arn]
            )
        )


    def create_user_pool(self):
        cognito_domain_base_name = "ai-bot-domain"
        # Create a hash of stack name + account + region for guaranteed uniqueness
        unique_string = f"{self.stack_name.lower()}-{Stack.of(self).account}"
        domain_prefix = f"{cognito_domain_base_name}-{unique_string}"
        domain_prefix = domain_prefix.strip('-')[:63]
        if self.self_signup  is not None:
             # cast the value if True, true, yes, y, T
             singup_condition = True if self.self_signup.lower() in ["true", "yes", "y", "t"] else False
        else:
            singup_condition = False
        self.user_pool = _cognito.UserPool(
            self, "AIbotUserPool",
            user_pool_name="AIbotUserPool",
            self_sign_up_enabled=singup_condition,
            # removal policy destroy
            removal_policy=RemovalPolicy.DESTROY,
            # add email as a standard attribute
            standard_attributes=_cognito.StandardAttributes(
                email=_cognito.StandardAttribute(
                    required=True,
                    mutable=True)),
            user_verification=_cognito.UserVerificationConfig(
                email_subject="Verify your email for your AIbot app!",
                email_body="Thanks for signing up to your AIbot app! Your verification code is {####}",
                email_style=_cognito.VerificationEmailStyle.CODE,
                sms_message="Thanks for signing up to your AIbot app! Your verification code is {####}"
            ),
            sign_in_aliases=_cognito.SignInAliases(
                email=True,
                phone=False,
                username=False))
        # Congito Domain
        self.domain = self.user_pool.add_domain("AIbotDomain",
            cognito_domain=_cognito.CognitoDomainOptions(
                domain_prefix=domain_prefix
            )
        )
        _cognito.CfnUserPoolGroup(self, "AIbotDefaultGroup",
            user_pool_id=self.user_pool.user_pool_id,
            # the properties below are optional
            description="default group for documents",
            group_name="default",
            precedence=1
        )

    def create_api_lambdas(self):
        self.api_back_signed_url = python.PythonFunction(self, "ApiBackendSignedUrl",
            entry="src/lambda/apigw",
            index="signed_url.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                    "BUCKET": self.s3_file_bucket.bucket_name,
                    "UPLOAD_PREFIX": "raw_docs/"
                },
            timeout=Duration.seconds(20),
        )
        self.api_back_configure = python.PythonFunction(self, "ApiBackendConfigure",
            entry="src/lambda/apigw",
            index="prompt_manager.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                    "PROMT_SYSTEM_SSM": "aibot_promt_system", 
                    "PROMT_CONTEXT_SSM": "aibot_promt_context"
                },
            timeout=Duration.seconds(20),
        )

        self.api_back_documents = python.PythonFunction(self, "ApiBackendDocuments",
            entry="src/lambda/apigw",
            index="crud.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                    "TABLE_NAME_DOCUMENTS": self.table_documents.table_name,
                    "STATE_MACHINE_DELETE": self.state_machine_delete.state_machine_arn,
                    "BUCKET_DOCUMENTS": self.s3_file_bucket.bucket_name,
                    "TABLE_NAME_BIG": self.table_chunk_big.table_name,
                    "TABLE_NAME_SMALL": self.table_chunk_small.table_name
                },
            timeout=Duration.seconds(20),
        )

        self.api_back_documents.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:Query"],
                resources=[self.table_documents.table_arn]
            )
        )
        # add invoke state machine to api_back_documents
        self.api_back_documents.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[self.state_machine_delete.state_machine_arn]
            )
        )
        # TODO add permisions to the api_back_configure to do SSM put
        self.api_back_configure.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:PutParameter"],
                resources=["arn:aws:ssm:*:*:parameter/aibot_promt_system", "arn:aws:ssm:*:*:parameter/aibot_promt_context"]
            )
        )
        self.api_back_configure.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=["arn:aws:ssm:*:*:parameter/aibot_promt_system", "arn:aws:ssm:*:*:parameter/aibot_promt_context"]
            )
        )
        self.s3_file_bucket.grant_put(self.api_back_signed_url)

    def create_api_gw(self):
        cloudfront_domain =  "https://"+self.cloudfront_website.distribution_domain_name
        self.api_gateway = apigateway.RestApi(
            self, "ApiGWBackend",
            rest_api_name="AIbotApiGateway",
            description="This is the AIbot API Gateway",
            cloud_watch_role=True,
            deploy_options=apigateway.StageOptions(
                logging_level=apigateway.MethodLoggingLevel.ERROR,
                access_log_destination=apigateway.LogGroupLogDestination(
                    logs.LogGroup(self, "ApiGatewayAccessLogs", retention=logs.RetentionDays.ONE_WEEK)
                )
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_methods=["*"],
                # TODO allow the cloufront distribution
                allow_origins=[cloudfront_domain],
                # allow_origins=["*"],
                allow_headers=["*"]),
            # deploy=False
                )
        # body models 
        # configure promt model
        model_prompt = apigateway.Model(
            self, "AIBotPromptModel",
            rest_api=self.api_gateway,
            content_type="application/json",
            description="AIBot Prompt model",
            model_name="AIBotPromptModel",
            schema=apigateway.JsonSchema(
                schema=apigateway.JsonSchemaVersion.DRAFT4,
                type=apigateway.JsonSchemaType.OBJECT,
                required=["system"],
                properties={
                    "system": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING
                    ),
                    "context": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING
                    )
                }
            )
        )
        # chat model
        model_chat = apigateway.Model(
            self, "AIBotChatModel",
            rest_api=self.api_gateway,
            content_type="application/json",
            description="AIBot Chat model",
            model_name="AIBotChatModel",
            schema=apigateway.JsonSchema(
                schema=apigateway.JsonSchemaVersion.DRAFT4,
                type=apigateway.JsonSchemaType.OBJECT,
                required=["sessionId", "inputTranscript"],
                properties={
                    "sessionId": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING
                    ),
                    "inputTranscript": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING
                    )
                }
            )
        )
        # document model
        model_document = apigateway.Model(
            self, "AIBotDocumentModel",
            rest_api=self.api_gateway,
            content_type="application/json",
            description="AIBot Document model",
            model_name="AIBotDocumentModel",
            schema=apigateway.JsonSchema(
                schema=apigateway.JsonSchemaVersion.DRAFT4,
                type=apigateway.JsonSchemaType.OBJECT,
                required=["group", "filename"],
                properties={
                    "group": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING
                    ),
                    "filename": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING
                    )
                }
            )
        )

        # api_back_signed
        api_back_signed_url_integration = apigateway.LambdaIntegration(self.api_back_signed_url,
                request_templates={"application/json": '{ "statusCode": "200" }'})
        self.api_backend_resource_presing = self.api_gateway.root.add_resource("presign")
        self.autorizer = apigateway.CognitoUserPoolsAuthorizer(
                self, "AIbotAuthorizer",
                cognito_user_pools=[self.user_pool])
        method_api_backend_presing_get = self.api_backend_resource_presing.add_method(
            "GET", api_back_signed_url_integration,
            authorization_type=apigateway.AuthorizationType.COGNITO,
            authorizer=self.autorizer,
            request_parameters={
                "method.request.querystring.file_name": True
            },
            request_validator_options={
                "validate_request_parameters": True,
                "request_validator_name": "validate-presing_get"
            }
        )

        # api_back_configure
        api_back_configure_integration = apigateway.LambdaIntegration(self.api_back_configure,
                request_templates={"application/json": '{ "statusCode": "200" }'})
        self.api_backend_resource_config = self.api_gateway.root.add_resource("configure")

        method_api_backend_configure_post = self.api_backend_resource_config.add_method(
            "POST", api_back_configure_integration,
            authorization_type=apigateway.AuthorizationType.COGNITO,
            authorizer=self.autorizer,
            request_validator = apigateway.RequestValidator(
                self, "ConfigurePostValidator",
                rest_api=self.api_gateway,
                request_validator_name="validate-configure_post",
                validate_request_body=True),
            request_models={
                "application/json": model_prompt
            }
        )
        method_api_backend_configure_get = self.api_backend_resource_config.add_method(
            "GET", api_back_configure_integration,
            authorization_type=apigateway.AuthorizationType.COGNITO,
            authorizer=self.autorizer,
            request_parameters={
                "method.request.querystring.prompt": True
            },
            request_validator_options={
                "validate_request_parameters": True,
                "request_validator_name": "validate-configure_get"
            }
        )

        # api_back_chat
        api_back_chat_integration = apigateway.LambdaIntegration(self.prediction_lambda,
                request_templates={"application/json": '{ "statusCode": "200" }'})
        self.api_backend_resource_chat = self.api_gateway.root.add_resource("chat")
        method_api_backend_chat_post = self.api_backend_resource_chat.add_method(
            "POST", api_back_chat_integration,
            authorization_type=apigateway.AuthorizationType.COGNITO,
            authorizer=self.autorizer,
            request_validator = apigateway.RequestValidator(
                self, "ChatPostValidator",
                rest_api=self.api_gateway,
                request_validator_name="validate-chat_post",
                validate_request_body=True),
            request_models={
                "application/json": model_chat
            }
        )
        # api_back_documents
        api_back_documents_integration = apigateway.LambdaIntegration(self.api_back_documents,
                request_templates={"application/json": '{ "statusCode": "200" }'})
        self.api_backend_resource_documents = self.api_gateway.root.add_resource("documents")

        method_api_backend_documents_get = self.api_backend_resource_documents.add_method(
            "GET", api_back_documents_integration,
            authorization_type=apigateway.AuthorizationType.COGNITO,
            authorizer=self.autorizer,
            request_parameters={},
            request_validator_options={
                "validate_request_parameters": True,
                "request_validator_name": "validate-documents_get"
            }
        )

        method_api_backend_documents_delete = self.api_backend_resource_documents.add_method(
            "DELETE", api_back_documents_integration,
            authorization_type=apigateway.AuthorizationType.COGNITO,
            authorizer=self.autorizer,
            request_validator = apigateway.RequestValidator(
                self, "DocumentsDeleteValidator",
                rest_api=self.api_gateway,
                request_validator_name="validate-documents_delete",
                validate_request_body=True),
            request_models={
                "application/json": model_document
            }
        )
        # deployment = apigateway.Deployment(self, "Deployment",
        #     api=self.api_gateway,
        #     description="This is the CodeWhisperer API Gateway Deployment")
        # stage = apigateway.Stage(self, "Stage",
        #     deployment=deployment,
        #     stage_name="prod",
        #     description="AIBotStage")

    def create_web_app(self):
         # an s3 bucket for the web page that uses the files in the web folder
        self.s3_website_bucket = s3.Bucket(
            self, 
            "AIbot-WebsiteBucket", 
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
            )
        # create log bucket for CF
        self.log_cf_bucket = s3.Bucket(
            self,
            "AIbot-LogBucket",
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            object_ownership=s3.ObjectOwnership.OBJECT_WRITER,  # Required for CloudFront logging
            access_control=s3.BucketAccessControl.LOG_DELIVERY_WRITE 
        )
        # Create Origin Access Control
        s3_origin = origins.S3BucketOrigin.with_origin_access_control(self.s3_website_bucket,
            origin_access_levels=[_cf.AccessLevel.READ, _cf.AccessLevel.LIST]
        )

        # a cloudfront distribution for the s3_website_bucket
        cf_props = {
            "default_root_object": "index.html",
            "enable_logging": True,
            "log_bucket": self.log_cf_bucket,
            "log_file_prefix": "cf-logs/",
            "default_behavior": _cf.BehaviorOptions(
                allowed_methods=_cf.AllowedMethods.ALLOW_ALL,
                viewer_protocol_policy=_cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                origin=s3_origin)
        }
        
        # Only add WAF if ARN is provided
        if self.waf_acl_arn:
            cf_props["web_acl_id"] = self.waf_acl_arn
            
        self.cloudfront_website = _cf.Distribution(
            self,
            "AIbotWebsiteDistribution",
            **cf_props)
        
        self.redirect_uri = "https://"+self.cloudfront_website.distribution_domain_name + "/fallback.html"
        # add permisions to the cloudfront distribution to CORS to the file bucket
        self.s3_file_bucket.add_cors_rule(
            # TODO allow the cloufront distribution
            # allow_origins=[cloudfront_domain],
            allowed_origins=['*'],
            allowed_methods=[s3.HttpMethods.PUT],
            allowed_headers=['*']
            )
        self.client = self.user_pool.add_client("AIBot-client",
            o_auth=_cognito.OAuthSettings(
                flows=_cognito.OAuthFlows(
                    implicit_code_grant=True
                ),
                # the cloudfront distribution root url
                callback_urls=[self.redirect_uri]
            ),
            auth_flows=_cognito.AuthFlow(
                user_password=True,
                user_srp=True
            )
        )
        self.sign_in_url = self.domain.sign_in_url(self.client,
            redirect_uri=self.redirect_uri
        )
    
    def build_del_document_state_machine(self):
        with open('chatbot/delete-stepfunction.json', 'r') as file:
            state_machine_def = file.read()
            
            

        # Create the state machine
        self.state_machine_delete = sfn.StateMachine(
            self, "AIbotSMDeletion",
            definition_body=sfn.DefinitionBody.from_string(state_machine_def)
        )
        # Grant the state machine permissions to access the DynamoDB table
        self.table_documents.grant_read_write_data(self.state_machine_delete.role)
        self.table_chunk_small.grant_read_write_data(self.state_machine_delete.role)
        self.table_chunk_big.grant_read_write_data(self.state_machine_delete.role)
        self.s3_file_bucket.grant_read_write(self.state_machine_delete.role)
    
    def build_parser_document_state_machine(self):
        with open('chatbot/llmparser-stepfunction.json', 'r') as file:
            state_machine_def = file.read()
            replace_arn = {
                "__READDOCS__": f"{self.step1.function_arn}",
                "__PAGEPROCESS__": f"{self.step2split.function_arn}",
                "__RAWDATAJOINER__": f"{self.step3joiner.function_arn}",
                "__CHUNKRAWDATA__": f"{self.step3.function_arn}",
                "__STORECHUNKDYNAMO__": f"{self.step4.function_arn}",
            }
            for key, value in replace_arn.items():
                state_machine_def = state_machine_def.replace(key, value)

        # Create the state machine
        self.state_machine_llm_parser = sfn.StateMachine(
            self, "AIbotSMLLMParser",
            definition_body=sfn.DefinitionBody.from_string(state_machine_def)
        )
        # Grant the state machine permissions to access the DynamoDB table
        self.table_documents.grant_read_write_data(self.state_machine_llm_parser.role)
        self.table_chunk_small.grant_read_write_data(self.state_machine_llm_parser.role)
        self.table_chunk_big.grant_read_write_data(self.state_machine_llm_parser.role)
        self.s3_file_bucket.grant_read_write(self.state_machine_llm_parser.role)
        ## add permisions to state_machine_llm_parser to invoke the lambda functions
        self.state_machine_llm_parser.add_to_role_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[
                    self.step1.function_arn + ":*",
                    self.step2split.function_arn + ":*",
                    self.step3.function_arn + ":*",
                    self.step3joiner.function_arn + ":*",
                    self.step4.function_arn + ":*",
                    self.step1.function_arn,
                    self.step2split.function_arn,
                    self.step3.function_arn,
                    self.step3joiner.function_arn,
                    self.step4.function_arn,
                ]
            )
        
        )
        role = iam.Role(self, "documentUploadedRole",
            assumed_by=iam.ServicePrincipal("events.amazonaws.com")
        )
        self.upload_rule.add_target(targets.SfnStateMachine(
            self.state_machine_llm_parser,
            role=role
        ))

    def create_state_machine(self):
        # add permisions to role to get ListBucket in the document bucket
        # task1 = tasks.LambdaInvoke(self, "ReadDocsTask",
        #     lambda_function=self.step1
        # )
        task2 = tasks.LambdaInvoke(self, "StoreRawDocsTask",
            lambda_function=self.step2
        )
        task3 = tasks.LambdaInvoke(self, "ChunkRawDataTask",
            lambda_function=self.step3
        )
        task4 = tasks.LambdaInvoke(self, "StoreChunkDynamoTask",
            lambda_function=self.step4
        )

        self.state_machine_textract = sfn.StateMachine(self, "AIbotSM",
            definition_body=sfn.DefinitionBody.from_chainable(task2.next(task3).next(task4))
        )
        self.state_machine_textract.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[
                    self.s3_file_bucket.bucket_arn,
                    f"{self.s3_file_bucket.bucket_arn}/*"
                ]
            )
        )

    def create_event_rules(self):
        self.upload_rule = events.Rule(self, "documentUploadedRule",
            event_pattern=events.EventPattern(
                source = ["aws.s3"],
                detail_type = ["Object Created"],
                detail = {
                    "bucket": {
                        "name": [self.s3_file_bucket.bucket_name]
                    },
                    "object": {
                        "key": [{"wildcard": "raw_docs/*"}]
                    }
                }
            )
        )

    def create_s3_bucket(self):
        self.s3_file_bucket = s3.Bucket(
            self, "AIbot-file-store",
            versioned=True,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            event_bridge_enabled=True,
            encryption=s3.BucketEncryption.KMS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(90)
                        )
                    ],
                    # expiration=Duration.days(365)
                )
            ]
        )

    def create_dynamo_tables(self):
        
        self.table_chunk_small = dynamodb.TableV2(
            self, "AIbot_rag_textract",
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="filename",
                type=dynamodb.AttributeType.STRING
            ),
            billing=dynamodb.Billing.on_demand(),
            removal_policy=RemovalPolicy.DESTROY
        )

        self.table_chunk_big = dynamodb.TableV2(
            self, "AIbot_rag_llm",
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="filename",
                type=dynamodb.AttributeType.STRING
            ),
            billing=dynamodb.Billing.on_demand(),
            removal_policy=RemovalPolicy.DESTROY
        )
        ## add secondary index to both tables
        self.table_chunk_small.add_global_secondary_index(
            index_name="group",
            partition_key=dynamodb.Attribute(name="group", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="filename", type=dynamodb.AttributeType.STRING),
            # projection_type=dynamodb.ProjectionType.KEYS_ONLY if the index was inverted we could just project the keys
            )
        
        self.table_chunk_big.add_global_secondary_index(
            index_name="group",
            partition_key=dynamodb.Attribute(name="group", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="filename", type=dynamodb.AttributeType.STRING),
            # projection_type=dynamodb.ProjectionType.KEYS_ONLY if the index was inverted we could just project the keys
            )


        self.table_conversation = dynamodb.TableV2(
            self, "AIbotConversationHistory",
            partition_key=dynamodb.Attribute(
                name="session_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing=dynamodb.Billing.on_demand(),
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="expiration_time",  # TTL attribute
        )

        self.table_documents = dynamodb.TableV2(
            self, "AIbotDocuments",
            partition_key=dynamodb.Attribute(
                name="group",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="filename",
                type=dynamodb.AttributeType.STRING
            ),
            billing=dynamodb.Billing.on_demand(),
            removal_policy=RemovalPolicy.DESTROY
        )

    def build_functions(self):
        self.step1 = python.PythonFunction(self, "ReadDocs",
            entry="src/lambda/step1",
            index="read_docs.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                "BUCKET_NAME": self.s3_file_bucket.bucket_name,
                "DOCUMENT_TABLE": self.table_documents.table_name,
                "SNS_TOPIC": self.sns_topic.topic_arn,
                "TEXTRACT_ROLE": self.sns_role.role_arn
                },
            timeout=Duration.seconds(900),
            memory_size=1024,
            layers=[
                python.PythonLayerVersion(self, "ReadDocs_layer",
                    entry="src/lambda/step1",
                    compatible_runtimes=[_lambda.Runtime.PYTHON_3_12]
                )
            ]
        )
        self.step2 = python.PythonFunction(self, "StoreRawDocs",
            entry="src/lambda/step2",
            index="store_raw_docs.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                "BUCKET_NAME": self.s3_file_bucket.bucket_name,
                },
            timeout=Duration.seconds(900),
            memory_size=1024,
        )

        self.step2split = python.PythonFunction(self, "PagesProcess",
            entry="src/lambda/step2split",
            index="llm_extractor.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                "DOCUMENTS_BUCKET_NAME": self.s3_file_bucket.bucket_name,
                "DOCUMENTS_TABLE_NAME": self.table_documents.table_name
                },
            timeout=Duration.seconds(900),
            memory_size=1024,
        )
        self.step3 = python.PythonFunction(self, "ChunkRawData",
            entry="src/lambda/step3",
            index="chunk_raw_data.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                "BUCKET_NAME": self.s3_file_bucket.bucket_name,
                "DEFAULT_TMP": "/tmp"
                },
            timeout=Duration.seconds(900),
            memory_size=1024,
            layers=[
                python.PythonLayerVersion(self, "ChunkRawData_layer",
                    entry="src/lambda/step3",
                    compatible_runtimes=[_lambda.Runtime.PYTHON_3_12]
                )
            ]
        )
        self.step3joiner = python.PythonFunction(self, "RawDataJoiner",
            entry="src/lambda/step3joiner",
            index="consolidator.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                "BUCKET_NAME": self.s3_file_bucket.bucket_name
                },
            timeout=Duration.seconds(900),
            memory_size=1024,
        )
        self.step4 = python.PythonFunction(self, "StoreChunkDynamo",
            entry="src/lambda/step4",
            index="store_chunk_dynamo.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            environment={
                "BUCKET_NAME": self.s3_file_bucket.bucket_name,
                "DYNAMO_TABLE_TEXTRACT": self.table_chunk_small.table_name,
                "DYNAMO_TABLE_LLM": self.table_chunk_big.table_name,
                },
            timeout=Duration.seconds(900),
            memory_size=1024,
            # layers=[
            #     python.PythonLayerVersion(self, "StoreChunkDynamo_layer",
            #         entry="src/lambda/step4",
            #         compatible_runtimes=[_lambda.Runtime.PYTHON_3_12]
            #     )
            # ]
        )

        # Permisions
        self.s3_file_bucket.grant_read_write(self.step1)
        self.s3_file_bucket.grant_read_write(self.step2)
        self.s3_file_bucket.grant_read_write(self.step3)
        self.s3_file_bucket.grant_read_write(self.step4)
        ## TODO remove the following
        # add permisions to all buckets to step4 function
        self.step4.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:*"],
                resources=["*"]
            ))

        self.table_chunk_small.grant_read_write_data(self.step4)
        self.table_chunk_big.grant_read_write_data(self.step4)
        self.table_documents.grant_read_write_data(self.step1)

        self.step4.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    #"arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3*",
                    # arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1 
                    "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
                ]
            )
        )
        # add StartDocumentTextDetection
        self.step1.add_to_role_policy(
            iam.PolicyStatement(
                actions=["textract:StartDocumentTextDetection","textract:GetDocumentTextDetection"],
                resources=["*"]
            ))
        
        # add permisions to the lambda to be invoked by sns

        self.step2split.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject", 
                    "s3:PutObjectAcl", 
                    "s3:PutObjectTagging",
                    "s3:PutObjectVersionAcl",
                    "s3:GetObject",
                    "s3:ListBucket"],
                resources=[self.s3_file_bucket.bucket_arn, self.s3_file_bucket.bucket_arn + "/*"]
            )
        )

        self.step2split.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "ssm:GetParameter"],
                resources=[
                    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude*",]
            )
        )
        self.step3joiner.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject", 
                    "s3:PutObjectAcl", 
                    "s3:PutObjectTagging",
                    "s3:PutObjectVersionAcl",
                    "s3:GetObject",
                    "s3:ListBucket"],
                resources=[self.s3_file_bucket.bucket_arn, self.s3_file_bucket.bucket_arn + "/*"]
            )
        )


    def build_query_lambda_func(self):
        # get ECR reposity If using codeCatalyst
        ecr_repo_image = os.environ.get("CommitId", None)
        ecr_repo = os.environ.get("RepositoryUri", "cdk-hnb659fds-container-assets-XXXXXXXXXX-us-east-1")
        if ecr_repo_image is None:
            lambda_image = _lambda.DockerImageCode.from_image_asset(
                directory="src/docker"
            )
        else:
            ecr_repo = ecr.Repository.from_repository_name(self, "AIBotEcr", ecr_repo)
            lambda_image = _lambda.DockerImageCode.from_ecr(
                repository = ecr_repo,
                tag_or_digest = ecr_repo_image 
            )

        self.prediction_lambda = _lambda.DockerImageFunction(
            scope=self,
            id="AIBotDockerLambda",
            function_name="AI-QnA-Bot",
            code=lambda_image,
            timeout=Duration.seconds(120),
            memory_size=1024,
            environment={
                "DYNAMO_TABLE": self.table_conversation.table_name,
                "DYNAMO_TABLE_TEXTRACT": self.table_chunk_small.table_name,
                "DYNAMO_TABLE_LLM": self.table_chunk_big.table_name,
                "TOLERANCE": "0.3",
                "MODEL_ID": "anthropic.claude-3-haiku-20240307-v1:0",
                "PROMT_SYSTEM_SSM": "aibot_promt_system",
                "PROMT_CONTEXT_SSM": "aibot_promt_context"
            }
        )
        self.table_conversation.grant_read_write_data(self.prediction_lambda)
        self.table_chunk_big.grant_read_data(self.prediction_lambda)
        self.table_chunk_small.grant_read_data(self.prediction_lambda)
        # create the iam policy
        self.prediction_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "ssm:GetParameter"],
                resources=[
                    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude*",
                    # arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1 
                    "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
                    "arn:aws:ssm:*:*:parameter/aibot_promt_system",
                    "arn:aws:ssm:*:*:parameter/aibot_promt_context"
                ]
            )
        )