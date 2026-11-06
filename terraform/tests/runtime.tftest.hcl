mock_provider "aws" {
  override_during = plan
  source          = "./tests/mocks"
}

variables {
  backend_image_digest         = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  backend_source_revision      = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  postgres_engine_version      = "17.6"
  db_final_snapshot_identifier = "fitlog-demo-test-final-fixture"
  origin_verify_secret         = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  expected_account_id          = "123456789012"
  environment_name             = "fitlog-demo-test"
  availability_zones           = ["ap-northeast-1a", "ap-northeast-1c"]
}

# Only provider-computed identifiers are fixtures. Policies and rules stay real.
override_resource {
  override_during = plan
  target          = aws_vpc.foundation
  values          = { id = "vpc-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_internet_gateway.public
  values          = { id = "igw-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_security_group.boundary["ingress"]
  values          = { id = "sg-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_security_group.boundary["app"]
  values          = { id = "sg-00000000000000002" }
}
override_resource {
  override_during = plan
  target          = aws_security_group.boundary["database"]
  values          = { id = "sg-00000000000000003" }
}
override_resource {
  override_during = plan
  target          = aws_s3_bucket.private["static"]
  values          = { id = "fitlog-demo-test-static-123456789012-ap-northeast-1", arn = "arn:aws:s3:::fitlog-demo-test-static-123456789012-ap-northeast-1" }
}
override_resource {
  override_during = plan
  target          = aws_s3_bucket.private["media"]
  values          = { id = "fitlog-demo-test-media-123456789012-ap-northeast-1", arn = "arn:aws:s3:::fitlog-demo-test-media-123456789012-ap-northeast-1" }
}
override_resource {
  override_during = plan
  target          = aws_ecr_repository.backend
  values          = { arn = "arn:aws:ecr:ap-northeast-1:123456789012:repository/fitlog-demo-test/backend", repository_url = "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/fitlog-demo-test/backend" }
}
override_resource {
  override_during = plan
  target          = aws_cloudwatch_log_group.backend
  values          = { arn = "arn:aws:logs:ap-northeast-1:123456789012:log-group:/fitlog/fitlog-demo-test/backend" }
}

override_resource {
  override_during = plan
  target          = aws_iam_role.ecs["task"]
  values          = { id = "fitlog-demo-test-task", arn = "arn:aws:iam::123456789012:role/fitlog-demo-test-task" }
}
override_resource {
  override_during = plan
  target          = aws_iam_role.ecs["execution"]
  values          = { id = "fitlog-demo-test-execution", arn = "arn:aws:iam::123456789012:role/fitlog-demo-test-execution" }
}
override_resource {
  override_during = plan
  target          = aws_vpc_security_group_ingress_rule.connection["app"]
  values          = { security_group_rule_id = "sgr-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_vpc_security_group_ingress_rule.connection["database"]
  values          = { security_group_rule_id = "sgr-00000000000000002" }
}
override_resource {
  override_during = plan
  target          = aws_vpc_security_group_egress_rule.connection["ingress"]
  values          = { security_group_rule_id = "sgr-00000000000000003" }
}
override_resource {
  override_during = plan
  target          = aws_vpc_security_group_egress_rule.connection["app"]
  values          = { security_group_rule_id = "sgr-00000000000000004" }
}
override_resource {
  override_during = plan
  target          = aws_vpc_security_group_egress_rule.https
  values          = { security_group_rule_id = "sgr-00000000000000005" }
}

override_resource {
  override_during = plan
  target          = aws_subnet.public["0"]
  values          = { id = "subnet-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_subnet.public["1"]
  values          = { id = "subnet-00000000000000002" }
}
override_resource {
  override_during = plan
  target          = aws_subnet.database["0"]
  values          = { id = "subnet-00000000000000003" }
}
override_resource {
  override_during = plan
  target          = aws_subnet.database["1"]
  values          = { id = "subnet-00000000000000004" }
}
override_resource {
  override_during = plan
  target          = aws_route_table.public
  values          = { id = "rtb-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_route_table.database
  values          = { id = "rtb-00000000000000002" }
}

override_resource {
  override_during = plan
  target          = aws_vpc_security_group_ingress_rule.cloudfront
  values          = { security_group_rule_id = "sgr-00000000000000006" }
}

# Independent oracle: approved FL-09B4 design, not provider-computed policies.
run "private_database_and_secrets" {
  command = plan
  assert {
    condition = (
      aws_db_subnet_group.runtime.subnet_ids == toset(["subnet-00000000000000003", "subnet-00000000000000004"]) &&
      aws_db_parameter_group.runtime.family == "postgres17" &&
      aws_db_parameter_group.runtime.parameter == toset([{ name = "rds.force_ssl", value = "1", apply_method = "pending-reboot" }]) &&
      aws_db_instance.runtime.parameter_group_name == aws_db_parameter_group.runtime.name &&
      aws_db_instance.runtime.db_subnet_group_name == aws_db_subnet_group.runtime.name &&
      aws_db_instance.runtime.vpc_security_group_ids == toset(["sg-00000000000000003"]) &&
      !aws_db_instance.runtime.publicly_accessible && !aws_db_instance.runtime.multi_az &&
      aws_db_instance.runtime.engine == "postgres" && aws_db_instance.runtime.engine_version == "17.6" &&
      aws_db_instance.runtime.instance_class == "db.t4g.micro" &&
      aws_db_instance.runtime.storage_type == "gp3" && aws_db_instance.runtime.allocated_storage == 20 && aws_db_instance.runtime.storage_encrypted &&
      aws_db_instance.runtime.identifier == "fitlog-demo-test" && aws_db_instance.runtime.db_name == "fitlog" &&
      aws_db_instance.runtime.username == "fitlog_admin" && aws_db_instance.runtime.port == 5432 &&
      aws_db_instance.runtime.manage_master_user_password && aws_db_instance.runtime.password == null && aws_db_instance.runtime.password_wo == null &&
      aws_db_instance.runtime.ca_cert_identifier == "rds-ca-rsa2048-g1" &&
      !aws_db_instance.runtime.auto_minor_version_upgrade && !aws_db_instance.runtime.allow_major_version_upgrade &&
      aws_db_instance.runtime.backup_retention_period == 1 && !aws_db_instance.runtime.delete_automated_backups &&
      aws_db_instance.runtime.deletion_protection && !aws_db_instance.runtime.skip_final_snapshot &&
      aws_db_instance.runtime.final_snapshot_identifier == "fitlog-demo-test-final-fixture" && !aws_db_instance.runtime.apply_immediately
    )
    error_message = "RDS must stay isolated, encrypted, TLS-only and protected against accidental destruction."
  }
  assert {
    condition = (
      aws_secretsmanager_secret.application.name == "fitlog-demo-test/application" &&
      aws_secretsmanager_secret.application.recovery_window_in_days == 7 &&
      aws_secretsmanager_secret.application.kms_key_id == null &&
      jsondecode(aws_iam_role_policy.application_secret.policy) == {
        Version   = "2012-10-17"
        Statement = [{ Sid = "ApplicationStartup", Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = ["arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fitlog-demo-test/application-AbCdEf"] }]
      } && aws_iam_role_policy.application_secret.role == "fitlog-demo-test-execution"
    )
    error_message = "Only the execution role may read exactly the application secret; no admin secret or wildcard."
  }
  assert {
    condition = output.database == {
      identifier        = "fitlog-demo-test", address = "fixture.ap-northeast-1.rds.amazonaws.com", port = 5432, name = "fitlog",
      master_secret_arn = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:rds!db-fixture-AbCdEf"
    } && output.application_secret_arn == "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fitlog-demo-test/application-AbCdEf"
    error_message = "Outputs must contain only DB/secret metadata, never passwords."
  }
}

run "stopped_fargate_and_complete_configuration" {
  command = plan
  assert {
    condition = (
      aws_ecs_task_definition.backend.requires_compatibilities == toset(["FARGATE"]) &&
      aws_ecs_task_definition.backend.network_mode == "awsvpc" &&
      aws_ecs_task_definition.backend.cpu == "256" && aws_ecs_task_definition.backend.memory == "1024" &&
      one(aws_ecs_task_definition.backend.runtime_platform).operating_system_family == "LINUX" &&
      one(aws_ecs_task_definition.backend.runtime_platform).cpu_architecture == "X86_64" &&
      aws_ecs_task_definition.backend.task_role_arn == "arn:aws:iam::123456789012:role/fitlog-demo-test-task" &&
      aws_ecs_task_definition.backend.execution_role_arn == "arn:aws:iam::123456789012:role/fitlog-demo-test-execution"
    )
    error_message = "Fargate needs the approved platform, resources and distinct task/execution roles."
  }
  assert {
    condition = jsondecode(aws_ecs_task_definition.backend.container_definitions) == [{
      name         = "backend", essential = true,
      image        = "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/fitlog-demo-test/backend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      portMappings = [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }],
      environment = [
        { name = "AWS_REGION", value = "ap-northeast-1" },
        { name = "DJANGO_SETTINGS_MODULE", value = "config.production" },
        { name = "FITLOG_APP_VERSION", value = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" },
        { name = "FITLOG_AUTH_CLIENT_IP_SOURCE", value = "remote_addr" },
        { name = "FITLOG_ENV", value = "production" },
        { name = "FITLOG_LOG_FORMAT", value = "json" },
        { name = "FITLOG_PUBLIC_HOST", value = "dfitlogtest.cloudfront.net" },
        { name = "FITLOG_TRUST_PROXY", value = "0" },
        { name = "POSTGRES_DB", value = "fitlog" },
        { name = "POSTGRES_HOST", value = "fixture.ap-northeast-1.rds.amazonaws.com" },
        { name = "POSTGRES_PORT", value = "5432" },
        { name = "POSTGRES_SSLROOTCERT", value = "/app/certs/rds-ap-northeast-1-bundle.pem" },
        { name = "POSTGRES_USER", value = "fitlog_app" },
        { name = "PRIVATE_MEDIA_BACKEND", value = "s3" },
        { name = "PRIVATE_MEDIA_BUCKET", value = "fitlog-demo-test-media-123456789012-ap-northeast-1" },
        { name = "PRIVATE_MEDIA_EXPECTED_OWNER", value = "123456789012" }
      ],
      secrets = [
        { name = "DJANGO_SECRET_KEY", valueFrom = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fitlog-demo-test/application-AbCdEf:DJANGO_SECRET_KEY::" },
        { name = "AUTH_RATE_LIMIT_HMAC_KEY", valueFrom = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fitlog-demo-test/application-AbCdEf:AUTH_RATE_LIMIT_HMAC_KEY::" },
        { name = "POSTGRES_PASSWORD", valueFrom = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fitlog-demo-test/application-AbCdEf:POSTGRES_PASSWORD::" }
      ],
      logConfiguration = { logDriver = "awslogs", options = {
        awslogs-group = "/fitlog/fitlog-demo-test/backend", awslogs-region = "ap-northeast-1", awslogs-stream-prefix = "backend", mode = "non-blocking", max-buffer-size = "4m"
      } }
    }]
    error_message = "The complete task JSON must contain only the approved image, environment, secret references and safe logging."
  }
  assert {
    condition = (
      aws_ecs_service.backend.cluster == aws_ecs_cluster.runtime.id &&
      aws_ecs_service.backend.task_definition == aws_ecs_task_definition.backend.arn &&
      aws_ecs_service.backend.launch_type == "FARGATE" && aws_ecs_service.backend.platform_version == "1.4.0" &&
      aws_ecs_service.backend.desired_count == 0 && !aws_ecs_service.backend.enable_execute_command &&
      !aws_ecs_service.backend.wait_for_steady_state &&
      aws_ecs_service.backend.deployment_minimum_healthy_percent == 100 && aws_ecs_service.backend.deployment_maximum_percent == 200 &&
      one(aws_ecs_service.backend.deployment_circuit_breaker).enable && one(aws_ecs_service.backend.deployment_circuit_breaker).rollback &&
      aws_ecs_service.backend.health_check_grace_period_seconds == 60 &&
      one(aws_ecs_service.backend.network_configuration).assign_public_ip &&
      one(aws_ecs_service.backend.network_configuration).subnets == toset(["subnet-00000000000000001", "subnet-00000000000000002"]) &&
      one(aws_ecs_service.backend.network_configuration).security_groups == toset(["sg-00000000000000002"]) &&
      length(aws_ecs_service.backend.load_balancer) == 1 &&
      one(aws_ecs_service.backend.load_balancer).target_group_arn == "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:targetgroup/fitlog-demo-test/0000000000000000" &&
      one(aws_ecs_service.backend.load_balancer).container_name == "backend" && one(aws_ecs_service.backend.load_balancer).container_port == 8000 &&
      one(aws_ecs_service.backend.load_balancer).elb_name == null && length(one(aws_ecs_service.backend.load_balancer).advanced_configuration) == 0
    )
    error_message = "Service must default stopped, register only this backend target and use the approved SG/public subnets."
  }
}

run "flags_000" {
  command = plan
  variables {
    enable_backend_service     = false
    enable_proxy_trust         = false
    enable_public_distribution = false
  }
  assert {
    condition     = aws_ecs_service.backend.desired_count == 0 && aws_cloudfront_distribution.edge.enabled == false && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_TRUST_PROXY"] == "0" && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_AUTH_CLIENT_IP_SOURCE"] == "remote_addr"
    error_message = "Service/public/proxy flags must remain independent, explicit and consistent."
  }
}

run "flags_001" {
  command = plan
  variables {
    enable_backend_service     = false
    enable_proxy_trust         = false
    enable_public_distribution = true
  }
  expect_failures = [aws_cloudfront_distribution.edge]
}

run "flags_010" {
  command = plan
  variables {
    enable_backend_service     = false
    enable_proxy_trust         = true
    enable_public_distribution = false
  }
  assert {
    condition     = aws_ecs_service.backend.desired_count == 0 && aws_cloudfront_distribution.edge.enabled == false && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_TRUST_PROXY"] == "1" && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_AUTH_CLIENT_IP_SOURCE"] == "cloudfront"
    error_message = "Service/public/proxy flags must remain independent, explicit and consistent."
  }
}

run "flags_011" {
  command = plan
  variables {
    enable_backend_service     = false
    enable_proxy_trust         = true
    enable_public_distribution = true
  }
  expect_failures = [aws_cloudfront_distribution.edge]
}

run "flags_100" {
  command = plan
  variables {
    enable_backend_service     = true
    enable_proxy_trust         = false
    enable_public_distribution = false
  }
  assert {
    condition     = aws_ecs_service.backend.desired_count == 1 && aws_cloudfront_distribution.edge.enabled == false && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_TRUST_PROXY"] == "0" && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_AUTH_CLIENT_IP_SOURCE"] == "remote_addr"
    error_message = "Service/public/proxy flags must remain independent, explicit and consistent."
  }
}

run "flags_101" {
  command = plan
  variables {
    enable_backend_service     = true
    enable_proxy_trust         = false
    enable_public_distribution = true
  }
  expect_failures = [aws_cloudfront_distribution.edge]
}

run "flags_110" {
  command = plan
  variables {
    enable_backend_service     = true
    enable_proxy_trust         = true
    enable_public_distribution = false
  }
  assert {
    condition     = aws_ecs_service.backend.desired_count == 1 && aws_cloudfront_distribution.edge.enabled == false && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_TRUST_PROXY"] == "1" && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_AUTH_CLIENT_IP_SOURCE"] == "cloudfront"
    error_message = "Service/public/proxy flags must remain independent, explicit and consistent."
  }
}

run "flags_111" {
  command = plan
  variables {
    enable_backend_service     = true
    enable_proxy_trust         = true
    enable_public_distribution = true
  }
  assert {
    condition     = aws_ecs_service.backend.desired_count == 1 && aws_cloudfront_distribution.edge.enabled == true && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_TRUST_PROXY"] == "1" && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_AUTH_CLIENT_IP_SOURCE"] == "cloudfront"
    error_message = "Service/public/proxy flags must remain independent, explicit and consistent."
  }
}

# Terraform nullable=false + default=false replaces explicit null with false.
run "null_flags_stay_disabled" {
  command = plan
  variables {
    enable_backend_service     = null
    enable_proxy_trust         = null
    enable_public_distribution = null
  }
  assert {
    condition     = aws_ecs_service.backend.desired_count == 0 && !aws_cloudfront_distribution.edge.enabled && { for e in jsondecode(aws_ecs_task_definition.backend.container_definitions)[0].environment : e.name => e.value }["FITLOG_TRUST_PROXY"] == "0"
    error_message = "Explicit null must never enable tasks, proxy trust or public distribution."
  }
}
