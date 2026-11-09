// ===========================================================================
// VB Jobs: COVER LETTER DOCX BUILDER (house template)
//
// Reusable across applications. The STYLE CONSTANTS and the layout helpers
// below are the house template, extracted from Alex's own resume DOCX and
// verified against it. Do not change them. Only change:
//   - the tagline in the header table
//   - the addressee block and the Re: line
//   - the five body paragraphs
//
// Requires: node, the `docx` npm package (preinstalled), and the headshot
// PNG at ./headshot.png (see claude/application-build-standard.md for where
// to get it).
//
// Build and verify:
//   node build_letter.js
//   python3 /mnt/skills/public/docx/scripts/office/soffice.py --headless \
//     --convert-to pdf Alex-Mercer-Cover-Letter-Company.docx
//   pdfinfo *.pdf | grep Pages          # must be 1
//   pdftoppm -jpeg -r 85 *.pdf p        # then LOOK at every page
// ===========================================================================

const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, ImageRun,
  Table, TableRow, TableCell, WidthType, BorderStyle, VerticalAlign,
  AlignmentType, LineRuleType,
} = require('docx');

const FONT = "Arial";
const TEXT = "1F2328";
const NAVY = "1A2F4B";
const TAGLINE = "33495F";
const CONTACT = "3D444D";
const SEP = "B0B0B0";

const NAME_SZ = 36;
const BODY_SZ = 20;
const SMALL_SZ = 17;

const TEXT_WIDTH = 10320;
const LEFT_COL = 8723;
const RIGHT_COL = 1597;
const NONE = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };

function sepRun(size = BODY_SZ) {
  return new TextRun({ text: "  |  ", font: FONT, size, color: SEP });
}
function emoji(ch, size = BODY_SZ) {
  return new TextRun({ text: ch, font: "Apple Color Emoji", size });
}
function body(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    spacing: { after: 140, line: 275, lineRule: LineRuleType.EXACT },
    children: [new TextRun({ text, font: FONT, size: BODY_SZ, color: TEXT })],
  });
}

const photo = fs.readFileSync("headshot.png");

const headerTable = new Table({
  columnWidths: [LEFT_COL, RIGHT_COL],
  width: { size: TEXT_WIDTH, type: WidthType.DXA },
  borders: { top: NONE, bottom: NONE, left: NONE, right: NONE, insideHorizontal: NONE, insideVertical: NONE },
  margins: { left: 0, right: 0 },
  rows: [new TableRow({
    children: [
      new TableCell({
        width: { size: LEFT_COL, type: WidthType.DXA },
        verticalAlign: VerticalAlign.CENTER,
        margins: { left: 0, right: 0 },
        children: [
          new Paragraph({
            spacing: { after: 50, line: 430, lineRule: LineRuleType.EXACT },
            children: [new TextRun({ text: "Mr. Alex Mercer", bold: true, font: FONT, size: NAME_SZ, color: NAVY, characterSpacing: 9 })],
          }),
          new Paragraph({
            spacing: { after: 80, line: 270, lineRule: LineRuleType.EXACT },
            children: [new TextRun({ text: "Software Product Manager | AI Automation & Applied AI", bold: true, font: FONT, size: BODY_SZ, color: TAGLINE })],
          }),
          new Paragraph({
            spacing: { after: 30, line: 230, lineRule: LineRuleType.EXACT },
            children: [
              new TextRun({ text: "Vancouver, BC, Canada ", font: FONT, size: SMALL_SZ, color: CONTACT }),
              sepRun(SMALL_SZ),
              new TextRun({ text: "Canadian Citizen", font: FONT, size: SMALL_SZ, color: CONTACT }),
            ],
          }),
          new Paragraph({
            spacing: { line: 230, lineRule: LineRuleType.EXACT },
            children: [
              new TextRun({ text: "+1 (555) 234-5678", font: FONT, size: SMALL_SZ, color: CONTACT }),
              sepRun(SMALL_SZ),
              new TextRun({ text: "alex.mercer@example.com", font: FONT, size: SMALL_SZ, color: CONTACT }),
              sepRun(SMALL_SZ),
              new TextRun({ text: "linkedin.com/in/alexander-mercer", font: FONT, size: SMALL_SZ, color: CONTACT }),
            ],
          }),
        ],
      }),
      new TableCell({
        width: { size: RIGHT_COL, type: WidthType.DXA },
        verticalAlign: VerticalAlign.CENTER,
        margins: { left: 0, right: 0 },
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new ImageRun({ data: photo, type: "png", transformation: { width: 94, height: 94 } })],
        })],
      }),
    ],
  })],
});

const children = [headerTable];

// Rule under the header, matching the resume's section-rule treatment
children.push(new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, space: 2, color: "C3CEDB" } },
  spacing: { before: 160, after: 200, line: 120, lineRule: LineRuleType.EXACT },
  children: [new TextRun({ text: "", font: FONT, size: 2 })],
}));

children.push(new Paragraph({
  spacing: { after: 30, line: 260, lineRule: LineRuleType.EXACT },
  children: [new TextRun({ text: "Hiring Team", font: FONT, size: BODY_SZ, color: CONTACT })],
}));
children.push(new Paragraph({
  spacing: { after: 180, line: 260, lineRule: LineRuleType.EXACT },
  children: [new TextRun({ text: "Re: AI Product Manager and Applied AI Product Roles", bold: true, font: FONT, size: BODY_SZ, color: NAVY })],
}));

children.push(new Paragraph({
  spacing: { after: 140, line: 275, lineRule: LineRuleType.EXACT },
  children: [new TextRun({ text: "Dear Hiring Team,", font: FONT, size: BODY_SZ, color: TEXT })],
}));

children.push(body("I am a Software Product Manager with 7+ years shipping technical products across IoT, automation and applied AI. My strongest fit is for roles where the product has to turn ambiguous workflows into usable systems: requirements, cross-functional delivery, stakeholder translation, launch, measurement and iteration."));
children.push(body("At Apex Industrial, I led a 14-person multidisciplinary team across software, hardware, firmware and UI/UX, coordinating digital and IoT product work across 12 departments without direct managerial authority. I owned requirements, prioritization, rollout and executive communication, while keeping the technical constraints readable for business stakeholders and the business goals clear for engineers."));
children.push(body("Before that, I launched Vanguard+, an IoT product combining a sensor device, mobile application and web portal, and I am a named inventor on patent-pending WO2023212799. The product connected hardware, software, supply chain and business case work, serving a customer base of around 10,000 and supporting new revenue streams through the device, subscription and in-app parts ordering."));
children.push(body("More recently, I have been building AI automation systems through TurboApply Agency and TurboApply.ai: AI receptionist agents, workflow automation, CRM and booking integrations, LLM-driven autofill, structured knowledge bases and conversion-focused web systems. I bring both product judgment and hands-on enough technical depth to work effectively with engineering teams on applied AI products."));
children.push(body("I am interested in AI Product Manager, Product Manager and applied automation roles where practical delivery matters more than buzzwords. I would welcome a conversation about how my product, IoT and AI automation background could help your team ship useful systems faster."));

children.push(new Paragraph({
  keepNext: true, keepLines: true,
  spacing: { before: 100, after: 280, line: 270, lineRule: LineRuleType.EXACT },
  children: [new TextRun({ text: "Sincerely,", font: FONT, size: BODY_SZ, color: TEXT })],
}));
children.push(new Paragraph({
  keepLines: true,
  spacing: { line: 270, lineRule: LineRuleType.EXACT },
  children: [new TextRun({ text: "Alex Mercer", bold: true, font: FONT, size: BODY_SZ, color: NAVY })],
}));

const doc = new Document({
  creator: "Alex Mercer",
  title: "Alex Mercer Cover Letter, Generic AI Product Manager",
  styles: { default: { document: { run: { font: FONT, size: BODY_SZ, color: TEXT } } } },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 737, bottom: 737, left: 793, right: 793 },
      },
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("Alex-Mercer-Cover-Letter-Generic-AI-Product-Manager.docx", buf);
  console.log("wrote generic cover letter docx");
});
