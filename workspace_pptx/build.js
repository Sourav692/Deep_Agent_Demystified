const pptxgen = require('pptxgenjs');
const path = require('path');
const html2pptx = require('./html2pptx');

(async () => {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_16x9';
  pptx.author = 'Sourav Banerjee';
  pptx.title = 'Beyond LangGraph: Engineering Deep Agents';

  const slides = [
    'slide1.html', 'slide2.html', 'slide3.html',
    'slide4.html', 'slide5.html', 'slide6.html', 'slide7.html'
  ];

  for (const f of slides) {
    await html2pptx(path.join(__dirname, 'slides', f), pptx);
  }

  await pptx.writeFile({ fileName: path.join(__dirname, 'deep-agents-presentation.pptx') });
  console.log('OK');
})().catch(e => { console.error(e); process.exit(1); });
