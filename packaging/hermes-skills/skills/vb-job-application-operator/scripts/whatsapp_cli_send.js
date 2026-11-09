const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const QRCode = require('qrcode');
const fs = require('fs');
const path = require('path');

function arg(name, fallback = null) {
  const idx = process.argv.indexOf('--' + name);
  if (idx >= 0 && idx + 1 < process.argv.length) return process.argv[idx + 1];
  return fallback;
}

const phone = arg('phone');
const messageFile = arg('message-file');
const company = arg('company', 'Unknown');
const role = arg('role', '');
const sourceUrl = arg('source-url', '');
const outPath = arg('out', path.resolve(__dirname, '../whatsapp-cli-send-result.json'));
const qrPngPath = arg('qr-png', path.resolve(__dirname, 'whatsapp-qr.png'));
const authDir = path.resolve(__dirname, 'auth');
const chromePath = process.env.WHATSAPP_CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const timeoutMs = Number(process.env.WHATSAPP_SEND_TIMEOUT_MS || 180000);

if (!phone || !messageFile) {
  console.error('Usage: node send.js --phone <digits> --message-file <path> [--company X] [--role Y] [--source-url URL] [--out path]');
  process.exit(2);
}

const message = fs.readFileSync(messageFile, 'utf8');
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.mkdirSync(authDir, { recursive: true });

function writeResult(obj) {
  const rec = {
    company,
    role,
    channel: 'whatsapp_cli',
    phone,
    source_url: sourceUrl,
    message_text: message,
    updated_at: new Date().toISOString(),
    ...obj,
  };
  fs.writeFileSync(outPath, JSON.stringify(rec, null, 2));
}

writeResult({ status: 'starting', auth_dir: authDir });

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: authDir, clientId: 'vb-jobs' }),
  puppeteer: {
    headless: false,
    executablePath: chromePath,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--use-mock-keychain',
      '--password-store=basic',
      '--user-data-dir=' + path.resolve(__dirname, 'chrome-profile'),
    ],
  },
});

let sent = false;
let qrSeen = false;

client.on('qr', async (qr) => {
  qrSeen = true;
  console.log('\nSCAN THIS WHATSAPP QR WITH YOUR PHONE:\n');
  qrcode.generate(qr, { small: true });
  try { await QRCode.toFile(qrPngPath, qr, { width: 512 }); } catch (e) {}
  writeResult({ status: 'qr_required', qr_png: qrPngPath, auth_dir: authDir });
});

client.on('authenticated', () => {
  writeResult({ status: 'authenticated', auth_dir: authDir });
});

client.on('auth_failure', (msg) => {
  writeResult({ status: 'auth_failure', error: String(msg), auth_dir: authDir });
  process.exit(1);
});

client.on('ready', async () => {
  try {
    const chatId = phone.replace(/[^0-9]/g, '') + '@c.us';
    const isRegistered = await client.isRegisteredUser(chatId);
    if (!isRegistered) {
      writeResult({ status: 'not_registered', chat_id: chatId, auth_dir: authDir });
      await client.destroy();
      process.exit(3);
    }
    const sentMsg = await client.sendMessage(chatId, message);
    sent = true;
    writeResult({
      status: 'sent',
      chat_id: chatId,
      message_id: sentMsg && sentMsg.id ? (sentMsg.id._serialized || JSON.stringify(sentMsg.id)) : null,
      auth_dir: authDir,
    });
    setTimeout(async () => { await client.destroy(); process.exit(0); }, 2000);
  } catch (e) {
    writeResult({ status: 'send_error', error: String(e && e.stack ? e.stack : e), auth_dir: authDir });
    try { await client.destroy(); } catch (_) {}
    process.exit(1);
  }
});

client.on('disconnected', (reason) => {
  if (!sent) writeResult({ status: 'disconnected_before_send', reason: String(reason), auth_dir: authDir });
});

setTimeout(async () => {
  if (!sent) {
    writeResult({
      status: qrSeen ? 'timeout_waiting_for_qr_scan_or_ready' : 'timeout_waiting_for_ready',
      auth_dir: authDir,
      qr_png: qrSeen ? qrPngPath : null,
    });
    try { await client.destroy(); } catch (_) {}
    process.exit(124);
  }
}, timeoutMs);

client.initialize().catch((e) => {
  writeResult({ status: 'init_error', error: String(e && e.stack ? e.stack : e), auth_dir: authDir });
  process.exit(1);
});
