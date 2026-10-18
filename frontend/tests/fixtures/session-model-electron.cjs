const { app, BrowserWindow } = require('electron')
if (process.env.PHASE4_TEST_USER_DATA) app.setPath('userData',process.env.PHASE4_TEST_USER_DATA)
app.commandLine.appendSwitch('force-device-scale-factor','1')
app.whenReady().then(async () => {
  const target=process.env.PHASE4_TEST_URL
  if (!/^http:\/\/127\.0\.0\.1:\d+\//.test(target || '')) throw new Error('Local test fixture required')
  const window=new BrowserWindow({width:421,height:484,useContentSize:true,frame:false,show:false,
    webPreferences:{contextIsolation:true,nodeIntegration:false,backgroundThrottling:false}})
  window.setContentSize(421,484)
  await window.loadURL(target)
})
app.on('window-all-closed',()=>app.quit())
