/*
On startup, connect to the 'ping_pong' app.
*/
console.log('Starting firefox command runner!')
var port = browser.runtime.connectNative('firefox_command_runner');

/*
Log that we received the message.
Then display a notification. The notification contains the URL,
which we read from the message.
*/
function notify(message) {
  console.log('background script received message');
  console.log(message)
}

/* thanks @Lemmon Hill for https://github.com/lennonhill/cookies-txt */
function formatCookie(co) {
  return [
    [
      co.httpOnly ? '#HttpOnly_' : '',
      !co.hostOnly && co.domain && !co.domain.startsWith('.') ? '.' : '',
      co.domain
    ].join(''),
    co.hostOnly ? 'FALSE' : 'TRUE',
    co.path,
    co.secure ? 'TRUE' : 'FALSE',
    co.session || !co.expirationDate ? 0 : co.expirationDate,
    co.name,
    co.value + '\n'
  ].join('\t');
}

/*
Assign `notify()` as a listener to messages from the content script.
*/
port.onMessage.addListener(notify);

/*
echo360 listener
In the case of echo360, we need to grab the url by inspecting the http traffic
*/
function echo360download(requestDetails) {
  if(requestDetails.url.includes("https://content.echo360.org") 
    && requestDetails.url.includes("av.m3u8")){
    console.log("firing echo360 download")
    browser.webRequest.onBeforeRequest.removeListener(echo360download);
    downloader(requestDetails.url)
  }
}

/*
Main download function
*/
function downloader(url){
  console.log('getting cookies for ' + url);
  browser.cookies.getAll({url: url}, function(cookie_list) {
    console.log('found ' + cookie_list.length + ' cookies');
    console.log('Sending: ' + url);
    console.log(JSON.stringify({url: url, cookies: cookie_list.map(formatCookie)}))
    port.postMessage(JSON.stringify({url: url, cookies: cookie_list.map(formatCookie)}));
  });
}


/*
On a click on the browser action, send the app a message.
*/
browser.browserAction.onClicked.addListener(function(tab) {
  if(tab.url.includes("https://echo360.org")) {
    browser.webRequest.onBeforeRequest.addListener(
      echo360download,
      {urls: ["<all_urls>"]}
    );
   browser.tabs.reload(); 
  }
  else{
    downloader(tab.url)
  }
});

/*
Fallback listener to remove the echo360download listener upon page load complete
In case where we do not find a suitable url to download
*/
browser.tabs.onUpdated.addListener(function(tabId, changeInfo, tab) {
    if (browser.webRequest.onBeforeRequest.hasListener(echo360download) && tab.status == "complete" && tab.active) { 
      console.log("removing listener in fallback")
      browser.webRequest.onBeforeRequest.removeListener(echo360download);
    }
});
