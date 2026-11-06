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

run "reject_short_account" {
  command = plan
  variables { expected_account_id = "123" }
  expect_failures = [var.expected_account_id]
}

run "reject_non_numeric_account" {
  command = plan
  variables { expected_account_id = "12345678901x" }
  expect_failures = [var.expected_account_id]
}

run "reject_other_project" {
  command = plan
  variables { environment_name = "other-demo-test" }
  expect_failures = [var.environment_name]
}

run "reject_empty_suffix" {
  command = plan
  variables { environment_name = "fitlog-demo-" }
  expect_failures = [var.environment_name]
}

run "reject_long_name" {
  command = plan
  variables { environment_name = "fitlog-demo-too-long-for-bucket-name" }
  expect_failures = [var.environment_name]
}

run "reject_duplicate_azs" {
  command = plan
  variables { availability_zones = ["ap-northeast-1a", "ap-northeast-1a"] }
  expect_failures = [var.availability_zones]
}

run "reject_single_az" {
  command = plan
  variables { availability_zones = ["ap-northeast-1a"] }
  expect_failures = [var.availability_zones]
}

run "reject_three_azs" {
  command = plan
  variables { availability_zones = ["ap-northeast-1a", "ap-northeast-1c", "ap-northeast-1d"] }
  expect_failures = [var.availability_zones]
}

run "reject_other_region" {
  command = plan
  variables { availability_zones = ["ap-northeast-1a", "us-east-1a"] }
  expect_failures = [var.availability_zones]
}

run "reject_empty_origin_secret" {
  command = plan
  variables { origin_verify_secret = "" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_short_origin_secret" {
  command = plan
  variables { origin_verify_secret = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcde" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_long_origin_secret" {
  command = plan
  variables { origin_verify_secret = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_uppercase_origin_secret" {
  command = plan
  variables { origin_verify_secret = "A123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_wildcard_origin_secret" {
  command = plan
  variables { origin_verify_secret = "*123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_question_mark_origin_secret" {
  command = plan
  variables { origin_verify_secret = "?123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" }
  expect_failures = [var.origin_verify_secret]
}
run "reject_whitespace_origin_secret" {
  command = plan
  variables { origin_verify_secret = " 123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" }
  expect_failures = [var.origin_verify_secret]
}

run "reject_digest_tag" {
  command = plan
  variables { backend_image_digest = "latest" }
  expect_failures = [var.backend_image_digest]
}

run "reject_digest_short" {
  command = plan
  variables { backend_image_digest = "sha256:abc" }
  expect_failures = [var.backend_image_digest]
}

run "reject_digest_repository" {
  command = plan
  variables { backend_image_digest = "other/repo@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
  expect_failures = [var.backend_image_digest]
}

run "reject_digest_uppercase" {
  command = plan
  variables { backend_image_digest = "sha256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" }
  expect_failures = [var.backend_image_digest]
}

run "reject_revision_short" {
  command = plan
  variables { backend_source_revision = "abc" }
  expect_failures = [var.backend_source_revision]
}

run "reject_revision_digest" {
  command = plan
  variables { backend_source_revision = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
  expect_failures = [var.backend_source_revision]
}

run "reject_postgres_major" {
  command = plan
  variables { postgres_engine_version = "18.1" }
  expect_failures = [var.postgres_engine_version]
}

run "reject_postgres_incomplete" {
  command = plan
  variables { postgres_engine_version = "17" }
  expect_failures = [var.postgres_engine_version]
}

run "reject_snapshot_prefix" {
  command = plan
  variables { db_final_snapshot_identifier = "other-final-demo" }
  expect_failures = [var.db_final_snapshot_identifier]
}

run "reject_snapshot_end" {
  command = plan
  variables { db_final_snapshot_identifier = "fitlog-demo-test-final-x-" }
  expect_failures = [var.db_final_snapshot_identifier]
}

run "reject_snapshot_double" {
  command = plan
  variables { db_final_snapshot_identifier = "fitlog-demo-test-final-x--y" }
  expect_failures = [var.db_final_snapshot_identifier]
}

run "reject_snapshot_long" {
  command = plan
  variables { db_final_snapshot_identifier = "fitlog-demo-test-final-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
  expect_failures = [var.db_final_snapshot_identifier]
}
