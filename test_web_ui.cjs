// Optional browser integration test: NODE_PATH must contain Playwright.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

(async () => {
  const url = process.env.ANY2ANY_TEST_URL || 'http://127.0.0.1:8765/';
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const context = await browser.newContext({viewport: {width: 560, height: 740}, acceptDownloads: true});
  if (url.startsWith('https://')) await context.grantPermissions(['local-network-access'], {origin: new URL(url).origin});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'any2any-ui-'));
  try {
    await page.goto(url);
    await page.waitForFunction(() => document.querySelector('#connection').classList.contains('connected'));
    assert.equal(await page.locator('input:not([type=file]):not([type=hidden])').count(), 0);
    assert.equal(await page.locator('#convert').isDisabled(), true);
    await page.screenshot({path: 'tools/ui-empty.png', fullPage: true});
    await fs.mkdir(path.join(folder, 'one'));
    await fs.mkdir(path.join(folder, 'two'));
    const first = path.join(folder, 'one', 'sample.srt');
    const second = path.join(folder, 'two', 'sample.ass');
    await fs.writeFile(first, '1\n00:00:00,000 --> 00:00:01,000\nHello\n');
    await fs.writeFile(second, '[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hello\n');
    await page.locator('#picker').setInputFiles(first);
    await page.waitForFunction(() => !document.querySelector('#add').disabled);
    await page.locator('#picker').setInputFiles(second);
    await page.waitForFunction(() => document.querySelectorAll('#files li').length === 2 && !document.querySelector('#add').disabled);
    await page.locator('#format').selectOption('vtt');
    await page.locator('#convert').click();
    await page.waitForFunction(() => !document.querySelector('#result').hidden, {timeout: 30000});
    assert.equal(await page.locator('#result-title').textContent(), 'Conversion complete');
    assert.equal(await page.locator('#errors').isVisible(), false);
    await page.screenshot({path: 'tools/ui-complete.png', fullPage: true});
    // Exercise the stream used after the OS save dialog, without displaying a dialog in headless mode.
    await page.evaluate(() => {
      window.showSaveFilePicker = async options => {
        window.savedName = options.suggestedName;
        window.savedChunks = [];
        return {createWritable: async () => new WritableStream({write(chunk) {window.savedChunks.push(...chunk);}})};
      };
    });
    await page.locator('#download').click();
    await page.waitForFunction(() => document.querySelector('#status').textContent === 'Download complete.');
    assert.equal(await page.evaluate(() => window.savedName), 'Any2Any.zip');
    const streamed = Buffer.from(await page.evaluate(() => window.savedChunks));
    assert.equal(streamed.subarray(0, 2).toString(), 'PK');
    assert(streamed.includes(Buffer.from('sample_srt.vtt')));
    assert(streamed.includes(Buffer.from('sample_ass.vtt')));
    // Exercise real browser downloads on platforms without the native save picker.
    await page.evaluate(() => {window.showSaveFilePicker = undefined;});
    const pending = page.waitForEvent('download');
    await page.locator('#download').click();
    const downloaded = await pending;
    assert.equal(downloaded.suggestedFilename(), 'Any2Any.zip');
    const local = path.join(folder, 'results.zip');
    await downloaded.saveAs(local);
    assert.deepEqual(await fs.readFile(local), streamed);
    for (const width of [360, 390, 560, 1200]) {
      await page.setViewportSize({width, height: 740});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Overflow at ${width}`);
    }
    await page.setViewportSize({width: 390, height: 740});
    await page.screenshot({path: 'tools/ui-mobile.png', fullPage: true});
    await page.locator('#format').selectOption('srt');
    await page.locator('#convert').click();
    await page.waitForFunction(() => !document.querySelector('#result').hidden && document.querySelector('#result-title').textContent === 'Conversion complete');
    assert.equal(await page.locator('#errors').isVisible(), false);
    await page.locator('#menu summary').click();
    await page.locator('#clear').click();
    await page.waitForFunction(() => document.querySelectorAll('#files li').length === 0);
    assert.equal(await page.locator('#files li').count(), 0);
    assert.equal(await page.locator('#result').isVisible(), false);
    const html = path.join(folder, 'document.html'), picture = path.join(folder, 'diagram.png');
    await fs.writeFile(html, '<html><body><p>Diagram</p><img src="diagram.png"></body></html>');
    const png = await page.evaluate(() => {
      const canvas = document.createElement('canvas'); canvas.width = 12; canvas.height = 9;
      const context = canvas.getContext('2d'); context.fillStyle = 'green'; context.fillRect(0, 0, 12, 9);
      return canvas.toDataURL('image/png').split(',')[1];
    });
    await fs.writeFile(picture, Buffer.from(png, 'base64'));
    await page.locator('#picker').setInputFiles([html, picture]);
    await page.waitForFunction(() => document.querySelectorAll('#files li').length === 2 && !document.querySelector('#add').disabled);
    await page.getByRole('button', {name: 'Use as a companion file: diagram.png', exact: true}).click();
    await page.locator('#format').selectOption('docx');
    await page.locator('#convert').click();
    await page.waitForFunction(() => !document.querySelector('#result').hidden, {timeout: 30000});
    assert.equal(await page.locator('#result-title').textContent(), 'Conversion complete');
    assert((await page.locator('#result-detail').textContent()).includes('document.docx'));
    const documentDownload = page.waitForEvent('download');
    await page.locator('#download').click();
    const savedDocument = await documentDownload;
    const documentPath = path.join(folder, 'result.docx');
    await savedDocument.saveAs(documentPath);
    assert((await fs.readFile(documentPath)).includes(Buffer.from('word/media/')), 'Document must embed its image');
    await page.locator('#menu summary').click();
    await page.locator('#clear').click();
    await page.waitForFunction(() => document.querySelectorAll('#files li').length === 0);
    await page.route('**/api/health', route => route.abort());
    await page.locator('#picker').setInputFiles(first);
    await page.waitForFunction(() => !document.querySelector('#add').disabled && document.querySelector('#status').classList.contains('error'));
    const unavailable = 'Local engine unavailable. Check the app and browser permissions.';
    assert.equal(await page.locator('#status').textContent(), unavailable);
    assert.equal(await page.locator('#files li').count(), 1);
    assert.equal(await page.locator('#convert').isDisabled(), true);
    await page.unroute('**/api/health');
    await page.locator('#connection').click();
    await page.waitForFunction(() => !document.querySelector('#add').disabled && document.querySelector('#format').options.length > 1);
    await page.route('**/api/batches/*/files', route => route.abort());
    await page.locator('#picker').setInputFiles(second);
    await page.waitForFunction(() => !document.querySelector('#add').disabled && document.querySelector('#status').classList.contains('error'));
    assert.equal(await page.locator('#status').textContent(), unavailable);
    assert.equal(await page.locator('#files li').count(), 2);
    assert.equal(await page.locator('#convert').isDisabled(), true);
    await page.unroute('**/api/batches/*/files');
    await page.locator('#connection').click();
    await page.waitForFunction(() => !document.querySelector('#add').disabled && !document.querySelector('#files').textContent.includes('waiting'));
    assert.equal(await page.locator('#status').textContent(), '2 files ready.');
    await page.getByRole('button', {name: 'Remove sample.ass', exact: true}).click();
    await page.getByRole('button', {name: 'Remove sample.srt', exact: true}).click();
    await page.waitForFunction(() => document.querySelectorAll('#files li').length === 0);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'add');
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.evaluate(() => document.activeElement.tagName), 'SUMMARY');
    assert.deepEqual(errors, []);
    console.log('PASS browser: multiple folders, format intersection, conversion, streamed save, real ZIP download, repeat conversion, recognized document companion, offline reconnect, remove, clear, keyboard and four viewport widths.');
  } finally {
    await context.close();
    await browser.close();
    await fs.rm(folder, {recursive: true, force: true});
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
