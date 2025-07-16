from aws_cdk import (
    Stack,
    aws_wafv2 as wafv2,
    CfnOutput
)
from constructs import Construct

class WafStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create the WAF ACL in us-east-1
        waf_acl = wafv2.CfnWebACL(self, 
            "AIBotCFACL",
            scope="CLOUDFRONT",
            name="AIBotCFACL",
            description="AIBotCFACL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="AIBotCFACL",
                sampled_requests_enabled=False
            ),
            rules=[
                # AWS-AWSManagedRulesCommonRuleSet
                {
                    "name": "AWS-AWSManagedRulesCommonRuleSet",
                    "priority": 0,
                    "statement": {
                        "managedRuleGroupStatement": {
                            "vendorName": "AWS",
                            "name": "AWSManagedRulesCommonRuleSet"
                        }
                    },
                    "overrideAction": {
                        "none": {}
                    },
                    "visibilityConfig": {
                        "cloudWatchMetricsEnabled": True,
                        "metricName": "AWS-AWSManagedRulesCommonRuleSet",
                        "sampledRequestsEnabled": False
                    }
                },
                # AWS-AWSManagedRulesAmazonIpReputationList
                {
                    "name": "AWS-AWSManagedRulesAmazonIpReputationList",
                    "priority": 1,
                    "statement": {
                        "managedRuleGroupStatement": {
                            "vendorName": "AWS",
                            "name": "AWSManagedRulesAmazonIpReputationList"
                        }
                    },
                    "overrideAction": {
                        "none": {}
                    },
                    "visibilityConfig": {
                        "cloudWatchMetricsEnabled": True,
                        "metricName": "AWS-AWSManagedRulesAmazonIpReputationList",
                        "sampledRequestsEnabled": False
                    }
                },
                # AWS-AWSManagedRulesKnownBadInputsRuleSet
                {
                    "name": "AWS-AWSManagedRulesKnownBadInputsRuleSet",
                    "priority": 2,
                    "statement": {
                        "managedRuleGroupStatement": {
                            "vendorName": "AWS",
                            "name": "AWSManagedRulesKnownBadInputsRuleSet"
                        }
                    },
                    "overrideAction": {
                        "none": {}
                    },
                    "visibilityConfig": {
                        "cloudWatchMetricsEnabled": True,
                        "metricName": "AWS-AWSManagedRulesKnownBadInputsRuleSet",
                        "sampledRequestsEnabled": False
                    }
                }
            ])
            
        # Export the WAF ACL ARN
        self.waf_acl_arn = waf_acl.attr_arn
        
        CfnOutput(self, "WafAclArn", 
            value=self.waf_acl_arn,
            description="ARN of the WAF ACL for CloudFront",
            export_name="AIBotWafAclArn")