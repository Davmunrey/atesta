// CloudFront viewer-request function: map clean URLs to the static export's files
// (/app -> /app.html, / -> /index.html). Paths with an extension pass through.
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.endsWith("/")) {
    request.uri = uri + "index.html";
  } else if (uri.lastIndexOf(".") <= uri.lastIndexOf("/")) {
    request.uri = uri + ".html";
  }
  return request;
}
