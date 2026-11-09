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
            children: [new TextRun({ text: "AI Solutions Engineer | Claude Code Skills & Agentic Workflows", bold: true, font: FONT, size: BODY_SZ, color: TAGLINE })],
          }),
          new Paragraph({
            spacing: { after: 30, line: 230, lineRule: LineRuleType.EXACT },
            children: [
              new TextRun({ text: "Batumi, Georgia ", font: FONT, size: SMALL_SZ, color: CONTACT }),
              emoji("\u{1F1EC}\u{1F1EA}", SMALL_SZ),
              sepRun(SMALL_SZ),
              new TextRun({ text: "Canadian Citizen ", font: FONT, size: SMALL_SZ, color: CONTACT }),
              emoji("\u{1F1E8}\u{1F1E6}", SMALL_SZ),
            ],
          }),
          new Paragraph({
            spacing: { line: 230, lineRule: LineRuleType.EXACT },
            children: [
              new TextRun({ text: "+1 555 234 5670", font: FONT, size: SMALL_SZ, color: CONTACT }),
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
  children: [new TextRun({ text: "Exadel Inc.", font: FONT, size: BODY_SZ, color: CONTACT })],
}));
children.push(new Paragraph({
  spacing: { after: 30, line: 260, lineRule: LineRuleType.EXACT },
  children: [new TextRun({ text: "Talent Acquisition Team", font: FONT, size: BODY_SZ, color: CONTACT })],
}));
children.push(new Paragraph({
  spacing: { after: 180, line: 260, lineRule: LineRuleType.EXACT },
  children: [new TextRun({ text: "Re: Lead AI Solutions Engineer (Bulgaria, Lithuania, Poland, Romania)", bold: true, font: FONT, size: BODY_SZ, color: NAVY })],
}));

children.push(new Paragraph({
  spacing: { after: 140, line: 275, lineRule: LineRuleType.EXACT },
  children: [new TextRun({ text: "Dear Exadel Hiring Team,", font: FONT, size: BODY_SZ, color: TEXT })],
}));

children.push(body("You are hiring someone to sit with business stakeholders, find the workflows worth encoding, and turn them into reusable Claude Code Skills that behave reliably. That is the work I already do rather than a direction I am moving toward. I run an AI automation studio where every engagement follows the same loop: run discovery with the business owner, map current state to target state, isolate the part worth encoding, write it as executable instructions with tool definitions and acceptance criteria, then test against real cases until the behaviour holds."));

children.push(body("The hands-on record is there. I designed and deployed HERMES, a multi-agent development team on a four-level hierarchy (operator, infrastructure layer, Team Lead, a five-role team plus a Coach) running on Docker Compose. I have authored reusable agent skills and system-prompt components, including a Software Architect and Architecture Auditor persona carrying a six-axis audit methodology, explicit severity definitions, a structured antipattern catalog and behavioural rules, plus a handoff protocol requiring the executing agent to produce the handoff artefact itself. I run these services on my own Hetzner and Cloudflare infrastructure, with prompts and configuration versioned so any regression is traceable and reversible, and I evaluate every skill against realistic scenarios and acceptance criteria defined before it ships, then tune it against real transcripts once it is live."));

children.push(body("The translation half is where I add the most. At Apex Industrial I ran 10 concurrent projects with a 14-person team across software, hardware, firmware and UI/UX, and aligned workstreams across 12 departments without direct managerial authority over any of them. That meant every requirement had to survive being read by a developer, a QA engineer and an executive without changing meaning, which is precisely the discipline a reusable skill demands. Before that I took Vanguard+ from a hunch to a launched IoT product serving around 10,000 customers, and I am a named inventor on patent-pending WO2023212799."));

children.push(body("On domain: I spent 20 months as product owner at TurboApply.ai, an AI-powered job application and outreach platform, where I owned requirements for LLM-driven autofill and matching against a structured knowledge base. That is HR technology, and it is the same retrieval-grounded pattern a skill relies on, where a curated reference set drives validated output rather than free generation. A global HR and benefits consultancy of the scale described is exactly where high-volume, template-driven, rule-heavy work makes reusable skills pay back quickly, and where getting the guardrails and the acceptance criteria right matters more than the model."));

children.push(body("On logistics, I am set up for exactly this kind of engagement. I am a Canadian citizen working with European and North American clients as a fully remote independent contractor, based in Batumi, Georgia at UTC+4, which is a full working-day overlap with Bulgaria, Lithuania, Poland and Romania, and I travel visa-free to the EU whenever onsite time is useful. I would welcome a conversation, and I am glad to walk you through the skills I have built and how I would approach the first workflows for your client."));

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
  title: "Alex Mercer Cover Letter, Exadel",
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
  fs.writeFileSync("Alex-Mercer-Cover-Letter-Exadel.docx", buf);
  console.log("wrote letter docx");
});
