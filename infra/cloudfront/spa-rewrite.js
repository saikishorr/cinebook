// CloudFront Function (viewer request) for the site bucket.
// Paths without a file extension, e.g. /booking/BK7F3A2, are React Router pages:
// serve index.html and let the app show the right page. Real files pass through.
function handler(event) {
  var request = event.request;
  if (!request.uri.includes('.')) {
    request.uri = '/index.html';
  }
  return request;
}
