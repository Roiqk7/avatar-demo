export const isSafari =
  typeof navigator !== 'undefined' &&
  /safari/i.test(navigator.userAgent) &&
  !/chrome|chromium|crios|fxios|edgios/i.test(navigator.userAgent)
