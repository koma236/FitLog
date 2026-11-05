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
