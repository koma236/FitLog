locals {
  backend_environment = {
    AWS_REGION                   = "ap-northeast-1"
    DJANGO_SETTINGS_MODULE       = "config.production"
    FITLOG_APP_VERSION           = var.backend_source_revision
    FITLOG_AUTH_CLIENT_IP_SOURCE = var.enable_proxy_trust ? "cloudfront" : "remote_addr"
    FITLOG_ENV                   = "production"
    FITLOG_LOG_FORMAT            = "json"
    FITLOG_PUBLIC_HOST           = aws_cloudfront_distribution.edge.domain_name
    FITLOG_TRUST_PROXY           = var.enable_proxy_trust ? "1" : "0"
    POSTGRES_DB                  = "fitlog"
    POSTGRES_HOST                = aws_db_instance.runtime.address
    POSTGRES_PORT                = "5432"
    POSTGRES_SSLROOTCERT         = "/app/certs/rds-ap-northeast-1-bundle.pem"
    POSTGRES_USER                = "fitlog_app"
    PRIVATE_MEDIA_BACKEND        = "s3"
    PRIVATE_MEDIA_BUCKET         = aws_s3_bucket.private["media"].bucket
    PRIVATE_MEDIA_EXPECTED_OWNER = var.expected_account_id
  }
}

resource "aws_ecs_cluster" "runtime" {
  name = var.environment_name
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.environment_name}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "1024"
  task_role_arn            = aws_iam_role.ecs["task"].arn
  execution_role_arn       = aws_iam_role.ecs["execution"].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name         = "backend"
    essential    = true
    image        = "${aws_ecr_repository.backend.repository_url}@${var.backend_image_digest}"
    portMappings = [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }]
    environment  = [for name, value in local.backend_environment : { name = name, value = value }]
    secrets = [for name in ["DJANGO_SECRET_KEY", "AUTH_RATE_LIMIT_HMAC_KEY", "POSTGRES_PASSWORD"] : {
      name = name, valueFrom = "${aws_secretsmanager_secret.application.arn}:${name}::"
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.backend.name
        awslogs-region        = "ap-northeast-1"
        awslogs-stream-prefix = "backend"
        mode                  = "non-blocking"
        max-buffer-size       = "4m"
      }
    }
  }])
}

resource "aws_ecs_service" "backend" {
  name                               = "${var.environment_name}-backend"
  cluster                            = aws_ecs_cluster.runtime.id
  task_definition                    = aws_ecs_task_definition.backend.arn
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  desired_count                      = var.enable_backend_service ? 1 : 0
  enable_execute_command             = false
  wait_for_steady_state              = false
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = [for subnet in aws_subnet.public : subnet.id]
    security_groups  = [aws_security_group.boundary["app"].id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "backend"
    container_port   = 8000
  }
  # IAM dependencies also keep permissions alive until service deletion finishes.
  depends_on = [
    aws_lb_listener.api,
    aws_lb_listener_rule.cloudfront,
    aws_route_table_association.public,
    aws_vpc_security_group_rules_exclusive.boundary,
    aws_iam_role_policy.media,
    aws_iam_role_policy.execution,
    aws_iam_role_policy.application_secret,
  ]
}
