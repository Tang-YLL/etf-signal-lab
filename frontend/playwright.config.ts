import {defineConfig, devices} from '@playwright/test'
import {fileURLToPath} from 'node:url'
import path from 'node:path'

const frontendDir=path.dirname(fileURLToPath(import.meta.url))
const repoDir=path.resolve(frontendDir,'..')
const python=process.env.E2E_PYTHON||path.join(repoDir,'backend','.venv','bin','python')
const server=path.join(repoDir,'scripts','e2e_server.py')

export default defineConfig({
  testDir:'./e2e',
  fullyParallel:false,
  workers:1,
  timeout:45_000,
  expect:{timeout:8_000},
  forbidOnly:!!process.env.CI,
  retries:process.env.CI?1:0,
  reporter:process.env.CI?[['dot'],['html',{outputFolder:'playwright-report',open:'never'}]]:[['list']],
  use:{
    baseURL:'http://127.0.0.1:5173',
    trace:'retain-on-failure',
    screenshot:'only-on-failure',
    video:'retain-on-failure',
  },
  projects:[
    {name:'chromium',use:{...devices['Desktop Chrome']}},
    {name:'mobile-chromium',use:{...devices['iPhone 13'],browserName:'chromium'}},
  ],
  webServer:[
    {
      command:`"${python}" "${server}"`,
      cwd:repoDir,
      url:'http://127.0.0.1:8000/api/v1/health',
      reuseExistingServer:false,
      timeout:120_000,
    },
    {
      command:'npm run dev -- --host 127.0.0.1 --port 5173',
      cwd:frontendDir,
      url:'http://127.0.0.1:5173',
      reuseExistingServer:false,
      timeout:120_000,
    },
  ],
})
