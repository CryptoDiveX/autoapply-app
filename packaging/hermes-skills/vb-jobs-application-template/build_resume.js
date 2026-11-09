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
              text: "AI Solutions Engineer | Claude Code Skills & Agentic Workflows",
              bold: true, font: FONT, size: BODY_SZ, color: TAGLINE,
            })],
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

// ---------- SUMMARY ----------
children.push(sectionHeading("Summary"));
children.push(new Paragraph({
  spacing: { line: 270, lineRule: LineRuleType.EXACT },
  children: [t("AI solutions engineer who builds agentic systems rather than only specifying them. Ships production AI agents for paying clients: versioned prompt systems, tool calls and integrations, structured outputs, guardrails, human escalation and live quality monitoring, on infrastructure he runs himself. Authors reusable agent skills, system-prompt components and MCP-connected workflows. Brings 7+ years of technical delivery, of which 6 years in product and project management, translating ambiguous business processes into executable, testable instructions across 12 departments without direct managerial authority. Electrical and electronics engineer by training, named inventor on patent-pending WO2023212799, available full time and fully remote at a full working-day overlap with Central and Eastern Europe.")],
}));

// ---------- BUILDS ----------
children.push(sectionHeading("Selected AI Engineering Builds"));
children.push(bullet([
  t("HERMES, multi-agent development team. ", { bold: true }),
  t("Designed and deployed a four-level agent hierarchy (operator, infrastructure layer, Team Lead, a five-role team of Fullstack/Tech Lead, DevOps, QA, PM and Designer, plus a Coach) on Docker Compose, with a single-entry-point communication rule and a design principle that security is never traded for functionality."),
]));
children.push(bullet([
  t("Reusable agent skills and personas. ", { bold: true }),
  t("Authored structured instruction sets for coding agents, including a Software Architect and Architecture Auditor persona carrying a six-axis audit methodology, severity definitions, a structured antipattern catalog and behavioural rules, plus a handoff protocol requiring the executing agent to produce the handoff artefact itself."),
]));
children.push(bullet([
  t("Self-hosted agent infrastructure and evaluation loop. ", { bold: true }),
  t("Runs LLM services on his own Hetzner and Cloudflare estate behind Docker, with versioned prompts and configuration for traceable rollback, scenario-based evaluation against real transcripts, and abuse filtering on public-facing agents."),
]));
children.push(bullet([
  t("Production automation pipelines. ", { bold: true }),
  t("A customer communications pipeline (messaging transport into self-hosted Chatwoot, orchestrated with n8n and NocoDB, webhook with immediate-200 response and upsert-by-id deduplication), a Whisper transcription and summarization service in Python, and a Docker-deployed vision assistant on the Claude Vision API."),
]));

// ---------- EXPERIENCE ----------
children.push(sectionHeading("Professional Experience", "\u{1F4BC}"));

children.push(roleHead("Freelancer & Delivery Lead", "May 2026 to Present"));
children.push(orgLine([
  orgLink("TurboApply Agency", "https://turboapply.agency/"),
  sepRun(ORG_SZ), orgBold("Batumi, Georgia"), sepRun(ORG_SZ), orgBold("Remote"),
]));
[
  "Founded and runs an AI automation studio serving health services, professional services and small business clients across North America and Europe.",
  "Designs and deploys custom AI agents handling lead qualification, appointment booking against a live calendar, CRM write-back and after-hours enquiries, measured on booked appointments and revenue rather than on model output.",
  "Builds API and connector integrations with REST endpoints, webhooks and n8n orchestration alongside custom Python services, so work moves without manual handling.",
  "Runs discovery interviews and current-state to target-state process mapping with clients, then converts the target process into agent instructions, tool definitions and acceptance criteria.",
  "Improves reliability iteratively after launch: reviews real conversations, tightens constraints and refusal behaviour, keeps a human escalation path open, and versions every prompt change so a regression can be rolled back.",
].forEach(b => children.push(bullet(b)));

children.push(roleHead("Software Product Manager, R&D", "Oct 2022 to May 2026"));
children.push(orgLine([
  orgLink("Apex Industrial", "https://apexindustrial.com/"),
  sepRun(ORG_SZ), orgBold("Vancouver, Canada"), sepRun(ORG_SZ), orgBold("Full Time"),
]));
[
  "Collaborated directly with business stakeholders and domain experts to capture objectives, processes and constraints, then translated them into structured requirements a developer, a QA engineer and the client would all read the same way.",
  "Led full-cycle software product development with a 14-person multidisciplinary team (software, hardware, firmware, UI/UX), aligning workstreams across 12 departments with no direct managerial authority over any of them.",
  "Ran 10 concurrent projects using Scrum and SMART principles, owning scope, timeline, risks and dependencies, and escalating early with options attached.",
  "Facilitated requirements workshops and ran gap analysis between the existing manual process and the proposed product: find the workflow worth encoding, then specify it precisely enough to execute.",
  "Introduced three new revenue streams (a co-invented patent-pending IoT device at 5x markup, an in-app premium subscription and in-app parts ordering) driving roughly a 10% increase in division revenue.",
  "Led projects through Architecture Review Boards with executive leadership and the CTO for security and compliance sign-off, maintained audit-ready decision logs, and drove 100% training and rollout adoption across departments.",
].forEach(b => children.push(bullet(b)));

children.push(roleHead("Project Manager, R&D Electronics Engineer", "Jul 2020 to Oct 2022"));
children.push(orgLine([
  orgLink("Vanguard Systems", "https://www.vanguardsystems.com/"),
  orgBold(", a Apex Industrial company"),
  sepRun(ORG_SZ), orgBold("Vancouver, Canada"), sepRun(ORG_SZ), orgBold("Full Time"),
]));
children.push(bullet([
  t("Launched Vanguard+, an IoT product (sensor device, mobile application and web portal), first of its kind in industrial equipment manufacturing, patent pending "),
  link("WO2023212799", "https://patentscope.wipo.int/search/en/detail.jsf?docId=WO2023212799"),
  t(", serving a base of around 10,000 global customers."),
]));
[
  "Personally designed the initial hardware iterations and early software prototypes to validate before build, then owned delivery across three engineering disciplines: requirements, estimation, PCB prototyping, full-stack software and supply chain.",
  "Built the business case and cost model, secured the initial development budget from executive sponsors, then used post-launch adoption and revenue results to secure follow-on budgets.",
  "Ran the internal ERP rollout: ERP integrated with the company CRM and the Vanguard+ mobile app, data migration, process changeover and training delivered personally.",
].forEach(b => children.push(bullet(b)));

children.push(roleHead("Partner & Product Owner, Board", "May 2024 to Jan 2026"));
children.push(orgLine([
  orgBold("TurboApply.ai"), sepRun(ORG_SZ), orgBold("Remote"),
  sepRun(ORG_SZ), orgBold("HR and recruiting technology"),
]));
[
  "Product owner for an AI-powered job application and outreach platform built by a fully distributed team across time zones: UI/UX, browser extension, front end, back end and tech lead.",
  "Owned requirements for LLM-driven autofill and matching against a structured knowledge base: a retrieval-grounded pattern where a curated reference set drives validated output rather than free generation. Wrote the user stories and acceptance criteria and owned scope trade-off calls.",
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
    new TextRun({ text: ", Vancouver, Canada. Elected Governor on the Board of Governors for three terms, Class Representative, Director at Student Association, Toastmasters.", font: FONT, size: ORG_SZ, color: EDUTEXT }),
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
children.push(skillsRow("AI Engineering & Agentic Systems:", "Claude Code, reusable agent skills and capability authoring, system prompt and persona design, structured instruction design, context engineering, tool use and function calling, MCP servers, multi-agent orchestration, spec-driven development, retrieval and knowledge base design, prompt versioning and rollback."));
children.push(skillsRow("Evaluation & Reliability:", "Acceptance criteria and realistic test scenarios, evaluation against real transcripts, tuning non-deterministic behaviour, guardrails and refusal behaviour, structured output validation, human escalation paths, decision and audit logging."));
children.push(skillsRow("Requirements & Stakeholder Translation:", "Discovery interviews, facilitated requirements workshops, current-state to target-state process mapping, gap analysis, user stories and acceptance criteria, executive reporting, cross-departmental rollout without direct authority."));
children.push(skillsRow("Technical:", "Python, Java, C++, C#, Linux, Docker and Docker Compose, GitHub, CI/CD, AWS, Hetzner, Cloudflare, REST APIs and webhooks, n8n, NocoDB, OpenAI API, OpenRouter, Whisper, Claude Vision API, relational databases, embedded systems, OpenCV."));
children.push(skillsRow("Tools:", "Claude, Claude Code, Codex, Hermes, OpenAI, Jira, Confluence, Wrike, Miro, Figma, GitHub, Salesforce, Excel, PowerPoint."));
children.push(skillsRow("Languages:", "English (fluent, professional proficiency), Russian (native), Ukrainian (fluent)."));
children.push(skillsRunsRow("Status:", [
  t("Canadian Citizen "), emoji("\u{1F1E8}\u{1F1E6}"), sepRun(),
  t("Batumi, Georgia (UTC+4) "), emoji("\u{1F1EC}\u{1F1EA}"), sepRun(),
  t("Full-time remote contractor, visa-free to the EU "), emoji("\u{1F1EA}\u{1F1FA}"), t("."),
]));

const doc = new Document({
  creator: "Alex Mercer",
  title: "Alex Mercer Resume, AI Solutions Engineer",
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
  fs.writeFileSync("Alex-Mercer-Resume-Exadel.docx", buf);
  console.log("wrote resume docx");
});
