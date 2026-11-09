// ===========================================================================
// VB Jobs: RESUME DOCX BUILDER (house template)
//
// Reusable across applications. The STYLE CONSTANTS and the layout helpers
// below are the house template, extracted from Alex's own resume DOCX and
// verified against it. Do not change them. Only change:
//   - the tagline in the header table
//   - the SUMMARY paragraph
//   - the section blocks and bullets
//   - the SKILLS rows
//
// Requires: node, the `docx` npm package (preinstalled), and the headshot
// PNG at ./headshot.png (see claude/application-build-standard.md for where
// to get it).
//
// Build and verify:
//   node build_resume.js
//   python3 /mnt/skills/public/docx/scripts/office/soffice.py --headless \
//     --convert-to pdf Alex-Mercer-Resume-Company.docx
//   pdfinfo *.pdf | grep Pages          # must be 2
//   pdftoppm -jpeg -r 85 *.pdf p        # then LOOK at every page
// ===========================================================================

const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, ExternalHyperlink, ImageRun,
  Table, TableRow, TableCell, WidthType, BorderStyle, VerticalAlign,
  AlignmentType, TabStopType, LevelFormat, LineRuleType,
} = require('docx');

// ---- Template style constants, lifted from the reference resume ----
const FONT = "Arial";
const TEXT = "1F2328";
const NAVY = "1A2F4B";
const TAGLINE = "33495F";
const CONTACT = "3D444D";
const SEP = "B0B0B0";
const ROLETITLE = "16212E";
const DATES = "4A525B";
const ORGBOLD = "3D5470";
const EDUTEXT = "454C55";

const NAME_SZ = 36;   // 18pt
const HEAD_SZ = 19;   // 9.5pt
const BODY_SZ = 20;   // 10pt
const ORG_SZ = 18;    // 9pt
const SMALL_SZ = 17;  // 8.5pt

const TEXT_WIDTH = 10320;      // 11906 - 793 - 793
const LEFT_COL = 8723;
const RIGHT_COL = 1597;

const NONE = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };

function t(text, o = {}) {
  return new TextRun(Object.assign({ text, font: FONT, size: BODY_SZ, color: TEXT }, o));
}
function sepRun(size = BODY_SZ) {
  return new TextRun({ text: "  |  ", font: FONT, size, color: SEP });
}
function link(text, url, o = {}) {
  return new ExternalHyperlink({
    children: [new TextRun(Object.assign({ text, font: FONT, size: BODY_SZ, style: "Hyperlink" }, o))],
    link: url,
  });
}
function emoji(ch, size = BODY_SZ) {
  const iconPath = ch === "💼" ? "emoji-briefcase.png" : (ch === "🎓" ? "emoji-graduation.png" : null);
  if (iconPath && fs.existsSync(iconPath)) {
    return new ImageRun({ data: fs.readFileSync(iconPath), type: "png", transformation: { width: 15, height: 15 } });
  }
  return new TextRun({ text: ch, font: "Apple Color Emoji", size });
}

function sectionHeading(text, icon) {
  const runs = [new TextRun({
    text: text.toUpperCase(), bold: true, font: FONT, size: HEAD_SZ,
    color: NAVY, characterSpacing: 14,
  })];
  if (icon) {
    runs.push(new TextRun({ text: " ", font: FONT, size: HEAD_SZ }));
    runs.push(emoji(icon, HEAD_SZ));
  }
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, space: 2, color: "C3CEDB" } },
    spacing: { before: 160, after: 80, line: 260, lineRule: LineRuleType.EXACT },
    children: runs,
  });
}

function roleHead(title, dates) {
  return new Paragraph({
    keepNext: true, keepLines: true,
    tabStops: [{ type: TabStopType.RIGHT, position: TEXT_WIDTH }],
    spacing: { before: 90, line: 270, lineRule: LineRuleType.EXACT },
    children: [
      new TextRun({ text: title, bold: true, font: FONT, size: BODY_SZ, color: ROLETITLE }),
      new TextRun({ text: "\t", font: FONT, size: BODY_SZ }),
      new TextRun({ text: dates, font: FONT, size: SMALL_SZ, color: DATES }),
    ],
  });
}

function orgLine(children) {
  return new Paragraph({
    keepNext: true, keepLines: true,
    spacing: { after: 40, line: 250, lineRule: LineRuleType.EXACT },
    children,
  });
}
function orgBold(text) {
  return new TextRun({ text, bold: true, font: FONT, size: ORG_SZ, color: ORGBOLD });
}
function orgLink(text, url) {
  return new ExternalHyperlink({
    children: [new TextRun({ text, bold: true, font: FONT, size: ORG_SZ, style: "Hyperlink" })],
    link: url,
  });
}

function bullet(children) {
  return new Paragraph({
    numbering: { reference: "vb-bullets", level: 0 },
    spacing: { after: 30, line: 270, lineRule: LineRuleType.EXACT },
    children: Array.isArray(children) ? children : [t(children)],
  });
}

function skillsRow(label, bodyText) {
  return new Paragraph({
    spacing: { after: 60, line: 270, lineRule: LineRuleType.EXACT },
    children: [
      new TextRun({ text: label + " ", bold: true, font: FONT, size: BODY_SZ, color: NAVY }),
      new TextRun({ text: bodyText, font: FONT, size: BODY_SZ, color: TEXT }),
    ],
  });
}
function skillsRunsRow(label, runs) {
  return new Paragraph({
    spacing: { after: 60, line: 270, lineRule: LineRuleType.EXACT },
    children: [
      new TextRun({ text: label + " ", bold: true, font: FONT, size: BODY_SZ, color: NAVY }),
      ...runs,
    ],
  });
}

// ---------- HEADER TABLE: text left, circular photo right ----------
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
            children: [new TextRun({
              text: "Mr. Alex Mercer", bold: true, font: FONT,
              size: NAME_SZ, color: NAVY, characterSpacing: 9,
            })],
          }),
          new Paragraph({
            spacing: { after: 60, line: 270, lineRule: LineRuleType.EXACT },
            children: [new TextRun({
              text: "Software Product Manager | AI Automation & Applied AI",
              bold: true, font: FONT, size: BODY_SZ, color: TAGLINE,
            })],
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
              sepRun(SMALL_SZ),
              new TextRun({ text: "x.com/alexanderx", font: FONT, size: SMALL_SZ, color: CONTACT }),
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

// ---------- SUMMARY ----------
children.push(sectionHeading("Summary"));
children.push(new Paragraph({
  spacing: { line: 270, lineRule: LineRuleType.EXACT },
  children: [t("Software Product Manager with 7+ years shipping technical products, including a patent-pending multimillion-dollar IoT product and AI-powered automation systems. Experienced owning requirements, leading cross-functional teams across engineering, design, hardware and firmware, and delivering solutions that improve operational efficiency. Currently building AI agents, workflow automation and conversion systems for small businesses. Seeking AI Product Manager roles focused on agents, automation or applied AI products.")],
}));

// ---------- EXPERIENCE ----------
children.push(sectionHeading("Professional Experience", "\u{1F4BC}"));

children.push(roleHead("Software Product Manager, R&D", "Oct 2022 to May 2026"));
children.push(orgLine([
  orgLink("Apex Industrial", "https://apexindustrial.com/"),
  sepRun(ORG_SZ), orgBold("Vancouver, Canada"), sepRun(ORG_SZ), orgBold("Full Time"),
]));
[
  "Led a 14-person multidisciplinary team across software, hardware, firmware and UI/UX to deliver digital and IoT product initiatives.",
  "Owned cross-departmental integration of new digital products and collaborated with executives on prioritization, rollout and business roadmap decisions.",
  "Translated ambiguous business requirements into user stories, acceptance criteria and technical constraints that engineering, QA and executive stakeholders could act on consistently.",
  "Ran 10 concurrent projects using Scrum and SMART principles, owning scope, timelines, risks and dependencies across 12 departments without direct managerial authority.",
  "Introduced three new revenue streams through an IoT device, in-app premium subscription and in-app parts ordering, driving roughly a 10% increase in division revenue.",
  "Led Architecture Review Board submissions with executive leadership and the CTO for security and compliance sign-off, maintaining decision logs and rollout documentation."
].forEach(b => children.push(bullet(b)));

children.push(roleHead("Project Manager, R&D Electronics Engineer", "Jul 2020 to Oct 2022"));
children.push(orgLine([
  orgLink("Vanguard Systems", "https://www.vanguardsystems.com/"),
  orgBold(", a Apex Industrial company"),
  sepRun(ORG_SZ), orgBold("Vancouver, Canada"), sepRun(ORG_SZ), orgBold("Full Time"),
]));
children.push(bullet([
  t("Launched Vanguard+, an IoT product (sensor device, mobile application and web portal), patent pending "),
  link("WO2023212799", "https://patentscope.wipo.int/search/en/detail.jsf?docId=WO2023212799"),
  t(", serving a base of around 10,000 global customers."),
]));
[
  "Owned end-to-end product delivery: requirements, hardware prototyping with PCB boards, full-stack software, supply chain, executive business cases and financial roadmaps.",
  "Personally designed early hardware iterations and software prototypes before they moved into production builds.",
  "Built an early computer vision MVP using OpenCV, a 3D camera and embedded systems for industrial human detection and safety.",
  "Built the business case and cost model, secured the initial development budget from executive sponsors, then used post-launch adoption and revenue results to secure follow-on budgets.",
  "Ran the internal ERP rollout: ERP integrated with the company CRM and Vanguard+ mobile app, data migration, process changeover and training delivered personally."
].forEach(b => children.push(bullet(b)));

children.push(roleHead("Freelancer & Delivery Lead", "May 2026 to Present"));
children.push(orgLine([
  orgLink("TurboApply Agency", "https://turboapply.agency/"),
  sepRun(ORG_SZ), orgBold("Batumi, Georgia"), sepRun(ORG_SZ), orgBold("Remote"),
]));
[
  "Founded and operates TurboApply Agency, an AI automation and web systems company serving health services, professional services and small business operations.",
  "Designed and deployed custom AI receptionist agents handling lead qualification, appointment booking, CRM updates and after-hours inquiries.",
  "Built end-to-end systems combining conversion-focused websites, AI workflows, CRM and booking integrations, and outreach automation focused on turning leads into booked revenue.",
  "Runs discovery interviews and process mapping with clients, then converts target workflows into agent instructions, tool definitions and acceptance criteria."
].forEach(b => children.push(bullet(b)));

children.push(roleHead("Partner & Product Owner, Board", "May 2024 to Jan 2026"));
children.push(orgLine([
  orgBold("TurboApply.ai"), sepRun(ORG_SZ), orgBold("Remote"), sepRun(ORG_SZ), orgBold("HR and recruiting technology"),
]));
[
  "Partner and Product Owner for an AI-powered job application and outreach platform built by a fully distributed team across UI/UX, browser extension, front end, back end and tech lead.",
  "Defined technical requirements and product specifications, managed cross-functional delivery, and drove business development and early go-to-market initiatives.",
  "Owned requirements for LLM-driven autofill and matching against a structured knowledge base, using curated reference data to drive validated output."
].forEach(b => children.push(bullet(b)));

children.push(roleHead("R&D Engineering, Co-op", "Sep 2018 to Aug 2019"));
children.push(orgLine([
  orgLink("Vanguard Systems", "https://www.vanguardsystems.com/"), sepRun(ORG_SZ), orgBold("Vancouver, Canada"), sepRun(ORG_SZ), orgBold("Full Time"),
]));
children.push(bullet("Developed an MVP for a human detector using OpenCV, a 3D camera and embedded systems to improve safety in industrial settings."));

children.push(roleHead("Elected Director, Board of Governors", "Jun 2017 to May 2020"));
children.push(orgLine([
  orgLink("British Columbia Institute of Technology", "https://www.bcit.ca/"), sepRun(ORG_SZ), orgBold("Vancouver, Canada"), sepRun(ORG_SZ), orgBold("Board"),
]));
[
  "Served as a three-term elected student representative on the Institute Board.",
  "Liaised directly with provincial and federal government officials, contributing to policy development and governance.",
  "Networked with chairs and CEOs of various companies to adopt best practices in corporate governance."
].forEach(b => children.push(bullet(b)));

// ---------- EDUCATION ----------
children.push(sectionHeading("Education", "\u{1F393}"));
children.push(roleHead("Bachelor of Engineering, Electrical and Electronics Engineering", "Sep 2016 to May 2020"));
children.push(new Paragraph({
  keepLines: true,
  spacing: { before: 20, after: 60, line: 250, lineRule: LineRuleType.EXACT },
  children: [
    new ExternalHyperlink({
      children: [new TextRun({ text: "British Columbia Institute of Technology", font: FONT, size: ORG_SZ, style: "Hyperlink" })],
      link: "https://www.bcit.ca/",
    }),
    new TextRun({ text: ", Vancouver, Canada. Governor at BCIT Board of Governors, Class Representative, Director at Student Association, Toastmasters.", font: FONT, size: ORG_SZ, color: EDUTEXT }),
  ],
}));
children.push(roleHead("Diploma, Mechatronics and Robotics", "Sep 2014 to May 2016"));
children.push(new Paragraph({
  keepLines: true,
  spacing: { before: 20, line: 250, lineRule: LineRuleType.EXACT },
  children: [
    new ExternalHyperlink({
      children: [new TextRun({ text: "British Columbia Institute of Technology", font: FONT, size: ORG_SZ, style: "Hyperlink" })],
      link: "https://www.bcit.ca/",
    }),
    new TextRun({ text: ", Vancouver, Canada. Class Representative, Presentation Idol.", font: FONT, size: ORG_SZ, color: EDUTEXT }),
  ],
}));

// ---------- SKILLS ----------
children.push(sectionHeading("Skills"));
children.push(skillsRow("Languages:", "English, Russian, Ukrainian."));
children.push(skillsRow("Product & Leadership:", "Product Ownership, Product Management, Business Development, R&D, Roadmapping, Cross-functional Team Leadership, Stakeholder Management, Go-to-Market, Product Launch, Customer Success, B2B, SaaS, Patenting, Cross-team Collaboration."));
children.push(skillsRow("AI & Automation:", "AI Agents, Workflow Automation, Generative AI Integrations, AI Receptionist, Conversational Systems, Prompt Systems, System Design for AI Products, Hermes Agents, Claude, Codex, OpenRouter, Spec Driven Development, Production Grade Deployments, GitHub, Hetzner, AWS, Bitwarden, CRM Integrations, Twenty CRM, Cloudflare, SEO, MCP Servers, Prompt Engineering, CI/CD, Bot Detection Filters."));
children.push(skillsRow("Technical:", "AWS, React Native, JavaScript, IoT Systems, Hardware-Firmware Integration, hardware development, firmware development, OpenCV, full-stack prototyping, Python, C, C++, Java, Android, Jira, Figma, Miro, Wrike, Confluence, GitHub, Salesforce, Conversica."));
children.push(skillsRunsRow("Travel and Status:", [
  t("Canadian Citizen"), sepRun(), t("USA NEXUS Holder"), sepRun(), t("Open to full-time AI product, product management and applied automation roles."),
]));


const doc = new Document({
  creator: "Alex Mercer",
  title: "Alex Mercer Resume, Generic AI Product Manager, Aligned Emoji v2",
  numbering: {
    config: [{
      reference: "vb-bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "•",
        alignment: AlignmentType.LEFT,
        style: {
          paragraph: { indent: { left: 225, hanging: 170 } },
          run: { font: FONT, size: BODY_SZ },
        },
      }],
    }],
  },
  styles: {
    default: { document: { run: { font: FONT, size: BODY_SZ, color: TEXT } } },
  },
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
  fs.writeFileSync("Alex-Mercer-Resume-Generic-AI-Product-Manager-Aligned-Emoji-v2.docx", buf);
  console.log("wrote generic resume docx");
});
