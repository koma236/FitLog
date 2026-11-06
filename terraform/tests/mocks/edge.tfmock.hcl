# Computed identifiers only. Planned policies and behavior settings remain real.
mock_data "aws_ec2_managed_prefix_list" {
  defaults = { id = "pl-00000000000000001" }
}
mock_resource "aws_cloudfront_distribution" {
  defaults = {
    id          = "EFITLOGTEST"
    arn         = "arn:aws:cloudfront::123456789012:distribution/EFITLOGTEST"
    domain_name = "dfitlogtest.cloudfront.net"
  }
}
mock_resource "aws_lb" {
  defaults = {
    arn      = "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:loadbalancer/app/fitlog-demo-test/0000000000000000"
    dns_name = "fitlog-demo-test.ap-northeast-1.elb.amazonaws.com"
  }
}
mock_resource "aws_lb_listener" {
  defaults = { arn = "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:listener/app/fitlog-demo-test/0000000000000000/1111111111111111" }
}
mock_resource "aws_lb_target_group" {
  defaults = { arn = "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:targetgroup/fitlog-demo-test/0000000000000000" }
}
mock_resource "aws_cloudfront_function" {
  defaults = { arn = "arn:aws:cloudfront::123456789012:function/fitlog-demo-test-client-ip" }
}
mock_resource "aws_cloudfront_origin_access_control" {
  defaults = { id = "EFITLOGOAC" }
}
mock_resource "aws_cloudfront_cache_policy" {
  defaults = { id = "00000000-0000-0000-0000-000000000001" }
}
mock_resource "aws_cloudfront_origin_request_policy" {
  defaults = { id = "00000000-0000-0000-0000-000000000002" }
}

mock_resource "aws_db_instance" {
  defaults = {
    address = "fixture.ap-northeast-1.rds.amazonaws.com"
    master_user_secret = [{
      secret_arn    = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:rds!db-fixture-AbCdEf"
      kms_key_id    = "arn:aws:kms:ap-northeast-1:123456789012:key/00000000-0000-0000-0000-000000000003"
      secret_status = "active"
    }]
  }
}

mock_resource "aws_secretsmanager_secret" {
  defaults = { arn = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fitlog-demo-test/application-AbCdEf" }
}

mock_resource "aws_ecr_repository" {
  defaults = { repository_url = "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/fitlog-demo-test/backend" }
}

mock_resource "aws_ecs_cluster" {
  defaults = { id = "arn:aws:ecs:ap-northeast-1:123456789012:cluster/fitlog-demo-test" }
}

mock_resource "aws_ecs_task_definition" {
  defaults = { arn = "arn:aws:ecs:ap-northeast-1:123456789012:task-definition/fitlog-demo-test-backend:1" }
}
