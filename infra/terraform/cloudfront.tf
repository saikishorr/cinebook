# Created in Part 12. The distribution itself is added here once the account is verified for CloudFront.
resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "cinebook-site-oac"
  description                       = "CloudFront reads the CineBook site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "spa_rewrite" {
  name    = "cinebook-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "React routes to index.html"
  publish = true
  code    = file("${path.module}/../cloudfront/spa-rewrite.js")
}
