"""Bounded AWS adapters; never persist SDK responses or log their contents."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

import boto3
import botocore.session
from botocore.config import Config

if TYPE_CHECKING:
    from mypy_boto3_cloudfront import CloudFrontClient
    from mypy_boto3_ecs import ECSClient
    from mypy_boto3_elbv2 import ElasticLoadBalancingv2Client
    from mypy_boto3_rds import RDSClient
    from mypy_boto3_secretsmanager import SecretsManagerClient
    from mypy_boto3_sts import STSClient

from operations.contract import KEYS, REGION, Request, SecretValues, require


@dataclass(frozen=True)
class DatabaseTarget:
    host: str
    administrator_secret: str


@dataclass
class Aws:
    sts: STSClient
    rds: RDSClient
    ecs: ECSClient
    secrets: SecretsManagerClient
    cloudfront: CloudFrontClient
    elbv2: ElasticLoadBalancingv2Client

    @classmethod
    def connect(cls) -> Aws:
        config = Config(region_name=REGION, connect_timeout=5, read_timeout=10,
                        retries={"total_max_attempts": 2})
        # Covers credential-chain clients too (AssumeRole / Web Identity), not just
        # the explicit clients below. A session override wins over env/config endpoints.
        core = botocore.session.get_session()
        core.set_config_variable("ignore_configured_endpoint_urls", True)
        session = boto3.Session(region_name=REGION, botocore_session=core)
        return cls(session.client("sts", config=config,
                                  endpoint_url="https://sts.ap-northeast-1.amazonaws.com"), session.client("rds", config=config,
                                  endpoint_url="https://rds.ap-northeast-1.amazonaws.com"),
                   session.client("ecs", config=config,
                                  endpoint_url="https://ecs.ap-northeast-1.amazonaws.com"),
                   session.client("secretsmanager", config=config,
                                  endpoint_url="https://secretsmanager.ap-northeast-1.amazonaws.com"),
                   # A fixed global endpoint bypasses the SDK's signing-region inference.
                   session.client("cloudfront", config=config.merge(Config(region_name="us-east-1")),
                                  endpoint_url="https://cloudfront.amazonaws.com"),
                   session.client("elbv2", config=config,
                                  endpoint_url="https://elasticloadbalancing.ap-northeast-1.amazonaws.com"))

    @staticmethod
    def tags(tags: Iterable[Mapping[str, object]], request: Request) -> None:
        actual = {tag["Key"]: tag["Value"] for tag in tags}
        require(actual.get("Project") == "FitLog"
                and actual.get("Environment") == request.environment)

    def inspect(self, request: Request) -> DatabaseTarget:
        require(self.sts.get_caller_identity()["Account"] == request.account)
        instances = self.rds.describe_db_instances(
            DBInstanceIdentifier=request.database,
        )["DBInstances"]
        require(len(instances) == 1)
        db = instances[0]
        require(db["DBInstanceIdentifier"] == request.environment
                and db["DBInstanceArn"].startswith(f"arn:aws:rds:{REGION}:{request.account}:db:")
                and db["Engine"] == "postgres" and db["EngineVersion"].startswith("17.")
                and db["DBName"] == "fitlog" and db["MasterUsername"] == "fitlog_admin"
                and db["PubliclyAccessible"] is False and db["DBInstanceStatus"] == "available"
                and db["Endpoint"]["Port"] == 5432)
        self.tags(db["TagList"], request)
        host = db["Endpoint"]["Address"]
        master = db["MasterUserSecret"]["SecretArn"]
        require(master.startswith(f"arn:aws:secretsmanager:{REGION}:{request.account}:secret:")
                and master != request.application_arn)
        secret = self.secrets.describe_secret(SecretId=request.application_arn)
        require(secret["ARN"] == request.application_arn
                and secret["Name"] == request.environment + "/application"
                and "DeletedDate" not in secret)
        self.tags(secret["Tags"], request)
        services = self.ecs.describe_services(cluster=request.environment,
                                               services=[request.service], include=["TAGS"])
        require(not services.get("failures") and len(services["services"]) == 1)
        service = services["services"][0]
        require(service["serviceName"] == request.service and service["status"] == "ACTIVE"
                and service["clusterArn"] == (
                    f"arn:aws:ecs:{REGION}:{request.account}:cluster/{request.environment}")
                and service["desiredCount"] == 0 and service["runningCount"] == 0
                and service["pendingCount"] == 0)
        self.tags(({"Key": tag["key"], "Value": tag["value"]}
                   for tag in service["tags"]), request)
        task = self.ecs.describe_task_definition(taskDefinition=service["taskDefinition"])[
            "taskDefinition"]
        require(task["taskDefinitionArn"].startswith(
            f"arn:aws:ecs:{REGION}:{request.account}:task-definition/{request.service}:"))
        containers = task["containerDefinitions"]
        require(len(containers) == 1 and containers[0]["name"] == "backend")
        container = containers[0]
        environment = {item["name"]: item["value"] for item in container["environment"]}
        for key, value in {"POSTGRES_HOST": host, "POSTGRES_PORT": "5432",
                           "POSTGRES_DB": "fitlog", "POSTGRES_USER": "fitlog_app"}.items():
            require(environment.get(key) == value)
        require({item["name"]: item["valueFrom"] for item in container["secrets"]} == {
            key: f"{request.application_arn}:{key}::" for key in KEYS})
        balancers = self.elbv2.describe_load_balancers(Names=[request.environment + "-api"])[
            "LoadBalancers"]
        require(len(balancers) == 1)
        balancer = balancers[0]
        balancer_arn = balancer["LoadBalancerArn"]
        require(balancer_arn.startswith(
            f"arn:aws:elasticloadbalancing:{REGION}:{request.account}:loadbalancer/app/"))
        self.tags(self.elbv2.describe_tags(ResourceArns=[balancer_arn])[
            "TagDescriptions"][0]["Tags"], request)
        distribution_arn = f"arn:aws:cloudfront::{request.account}:distribution/{request.distribution}"
        self.tags(self.cloudfront.list_tags_for_resource(Resource=distribution_arn)[
            "Tags"]["Items"], request)
        # This response contains the origin authentication header. Extract metadata only.
        distribution = self.cloudfront.get_distribution(Id=request.distribution)["Distribution"]
        require(distribution["ARN"] == distribution_arn and distribution["Status"] == "Deployed")
        config = distribution["DistributionConfig"]
        enabled = config["Enabled"]
        domains = [origin["DomainName"] for origin in config["Origins"]["Items"]
                   if origin["Id"] == "api"]
        del config, distribution
        require(enabled is False and domains == [balancer["DNSName"]])
        return DatabaseTarget(host, master)


@dataclass
class SecretStore:
    client: SecretsManagerClient
    request: Request

    def versions(self) -> list[tuple[str, list[str]]]:
        request = self.request
        versions: list[tuple[str, list[str]]] = []
        token = ""
        seen: set[str] = set()
        while True:
            if token:
                page = self.client.list_secret_version_ids(
                    SecretId=request.application_arn, IncludeDeprecated=True, NextToken=token)
            else:
                page = self.client.list_secret_version_ids(
                    SecretId=request.application_arn, IncludeDeprecated=True)
            versions.extend((item["VersionId"], item.get("VersionStages", []))
                            for item in page.get("Versions", []))
            token = page.get("NextToken", "")
            if not token:
                break
            require(token not in seen)
            seen.add(token)
        return versions

    def require_empty(self) -> None:
        require(not self.versions())

    def load_or_create(self, guard: Callable[[], None]) -> SecretValues:
        request = self.request
        guard()
        versions = self.versions()
        guard()
        if not versions:
            values = SecretValues.generate()
            guard()
            result = self.client.put_secret_value(
                SecretId=request.application_arn, ClientRequestToken=request.operation,
                SecretString=values.encode(), VersionStages=["AWSCURRENT"],
            )
            guard()
            require(result["ARN"] == request.application_arn
                    and result["VersionId"] == request.operation)
        else:
            require(versions == [(request.operation, ["AWSCURRENT"])])
            values = None
        guard()
        stored = self.client.get_secret_value(
            SecretId=request.application_arn, VersionId=request.operation, VersionStage="AWSCURRENT",
        )
        guard()
        require(stored["ARN"] == request.application_arn
                and stored["VersionId"] == request.operation
                and stored["VersionStages"] == ["AWSCURRENT"])
        loaded = SecretValues.decode(stored["SecretString"])
        require(values is None or loaded.encode() == values.encode())
        return loaded
