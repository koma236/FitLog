function handler(event) {
    // Replace the entire field, including any viewer-supplied multiValue.
    event.request.headers['x-fitlog-client-ip'] = { value: event.viewer.ip };
    return event.request;
}
