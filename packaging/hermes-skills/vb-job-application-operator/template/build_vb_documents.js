#!/usr/bin/env node
// ===========================================================================
// VB Jobs: PARAMETERIZED RESUME & COVER LETTER DOCX BUILDER (house template)
//
// Strictly preserves the exact style constants, DXA column widths, tab stops,
// hyperlinks, circular headshot.png, and emoji PNG icons from Alex's canonical
// VB Jobs house template (build_resume_aligned_emoji_v2.js & build_letter_generic.js).
// ===========================================================================

const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, ExternalHyperlink, ImageRun,
  Table, TableRow, TableCell, WidthType, BorderStyle, VerticalAlign,
  AlignmentType, TabStopType, LevelFormat, LineRuleType,
} = require('docx');

const TEMPLATE_DIR = __dirname;

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

const EMOJI_MAP = {
  "💼": { file: "emoji-briefcase.png", w: 15, h: 15 },
  "🎓": { file: "emoji-graduation.png", w: 15, h: 15 },
  "🇬🇪": { file: "emoji-ge.png", w: 12, h: 12 },
  "🇨🇦": { file: "emoji-ca.png", w: 12, h: 12 },
  "🇺🇸": { file: "emoji-us.png", w: 12, h: 12 },
  "🇪🇺": { file: "emoji-eu.png", w: 12, h: 12 },
};

function t(text, o = {}) {
  return new TextRun(Object.assign({ text: String(text || ""), font: FONT, size: BODY_SZ, color: TEXT }, o));
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
  const spec = EMOJI_MAP[ch];
  if (spec) {
    const iconPath = path.join(TEMPLATE_DIR, spec.file);
    if (fs.existsSync(iconPath)) {
      return new ImageRun({
        data: fs.readFileSync(iconPath),
        type: "png",
        transformation: { width: spec.w, height: spec.h },
      });
    }
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

function bulletWithPatentLink(textStr) {
  const str = String(textStr || "");
  if (str.includes("WO2023212799")) {
    const parts = str.split("WO2023212799");
    const runs = [];
    parts.forEach((part, idx) => {
      if (part) runs.push(t(part));
      if (idx < parts.length - 1) {
        runs.push(link("WO2023212799", "https://patentscope.wipo.int/search/en/detail.jsf?docId=WO2023212799"));
      }
    });
    return bullet(runs);
  }
  return bullet(str);
}

function bullet(children) {
  return new Paragraph({
    numbering: { reference: "vb-bullets", level: 0 },
    spacing: { after: 30, line: 270, lineRule: LineRuleType.EXACT },
    children: Array.isArray(children) ? children : [t(children)],
  });
}

function skillsRow(label, bodyText) {
  const cleanLabel = String(label || "").endsWith(":") ? String(label) : String(label) + ":";
  return new Paragraph({
    spacing: { after: 60, line: 270, lineRule: LineRuleType.EXACT },
    children: [
      new TextRun({ text: cleanLabel + " ", bold: true, font: FONT, size: BODY_SZ, color: NAVY }),
      new TextRun({ text: String(bodyText || ""), font: FONT, size: BODY_SZ, color: TEXT }),
    ],
  });
}

function skillsRunsRow(label, runs) {
  const cleanLabel = String(label || "").endsWith(":") ? String(label) : String(label) + ":";
  return new Paragraph({
    spacing: { after: 60, line: 270, lineRule: LineRuleType.EXACT },
    children: [
      new TextRun({ text: cleanLabel + " ", bold: true, font: FONT, size: BODY_SZ, color: NAVY }),
      ...runs,
    ],
  });
}

function buildHeaderTable(tagline, afterTagline = 60) {
  const photoPath = path.join(TEMPLATE_DIR, "headshot.png");
  const photo = fs.readFileSync(photoPath);
  return new Table({
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
              spacing: { after: afterTagline, line: 270, lineRule: LineRuleType.EXACT },
              children: [new TextRun({
                text: tagline || "Software Product Manager | AI Automation & Applied AI",
                bold: true, font: FONT, size: BODY_SZ, color: TAGLINE,
              })],
            }),
            new Paragraph({
              spacing: { after: 30, line: 230, lineRule: LineRuleType.EXACT },
              children: [
                new TextRun({ text: "Batumi, Georgia ", font: FONT, size: SMALL_SZ, color: CONTACT }),
                emoji("🇬🇪", SMALL_SZ),
                sepRun(SMALL_SZ),
                new TextRun({ text: "Canadian Citizen ", font: FONT, size: SMALL_SZ, color: CONTACT }),
                emoji("🇨🇦", SMALL_SZ),
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
                new TextRun({ text: "turboapply.agency", font: FONT, size: SMALL_SZ, color: CONTACT }),
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
}

function buildResumeDoc(payload) {
  const tagline = payload.tagline || "Software Product Manager | AI Automation & Applied AI";
  const children = [buildHeaderTable(tagline, 60)];

  // ---------- SUMMARY ----------
  children.push(sectionHeading("Summary"));
  children.push(new Paragraph({
    spacing: { line: 270, lineRule: LineRuleType.EXACT },
    children: [t(payload.summary || "Software Product Manager with 7+ years shipping technical products, including a patent-pending multimillion-dollar IoT product and AI-powered automation systems. Experienced owning requirements, leading cross-functional teams across engineering, design, hardware and firmware, and delivering solutions that improve operational efficiency. Currently building AI agents, workflow automation and conversion systems for small businesses.")],
  }));

  const roles = payload.roles || {};

  // ---------- EXPERIENCE ----------
  children.push(sectionHeading("Professional Experience", "💼"));

  // 1. Apex Industrial
  children.push(roleHead("Software Product Manager, R&D", "Oct 2022 to May 2026"));
  children.push(orgLine([
    orgLink("Apex Industrial", "https://apexindustrial.com/"),
    sepRun(ORG_SZ), orgBold("Vancouver, Canada"), sepRun(ORG_SZ), orgBold("Full Time"),
  ]));
  const apex_industrialBullets = Array.isArray(roles.apex_industrial) && roles.apex_industrial.length > 0 ? roles.apex_industrial : [
    "Led a 14-person multidisciplinary team across software, hardware, firmware and UI/UX to deliver digital and IoT product initiatives.",
    "Owned cross-departmental integration of new digital products and collaborated with executives on prioritization, rollout and business roadmap decisions.",
    "Translated ambiguous business requirements into user stories, acceptance criteria and technical constraints that engineering, QA and executive stakeholders could act on consistently.",
    "Ran 10 concurrent projects using Scrum and SMART principles, owning scope, timelines, risks and dependencies across 12 departments without direct managerial authority.",
    "Introduced three new revenue streams through an IoT device, in-app premium subscription and in-app parts ordering, driving roughly a 10% increase in division revenue.",
    "Led Architecture Review Board submissions with executive leadership and the CTO for security and compliance sign-off, maintaining decision logs and rollout documentation.",
  ];
  apex_industrialBullets.forEach(b => children.push(bulletWithPatentLink(b)));

  // 2. Vanguard Systems PM
  children.push(roleHead("Project Manager, R&D Electronics Engineer", "Jul 2020 to Oct 2022"));
  children.push(orgLine([
    orgLink("Vanguard Systems", "https://www.vanguardsystems.com/"),
    orgBold(", a Apex Industrial company"),
    sepRun(ORG_SZ), orgBold("Vancouver, Canada"), sepRun(ORG_SZ), orgBold("Full Time"),
  ]));
  const vanguardBullets = Array.isArray(roles.vanguard_pm) && roles.vanguard_pm.length > 0 ? roles.vanguard_pm : [
    "Launched Vanguard+, an IoT product (sensor device, mobile application and web portal), patent pending WO2023212799, serving a base of around 10,000 global customers.",
    "Owned end-to-end product delivery: requirements, hardware prototyping with PCB boards, full-stack software, supply chain, executive business cases and financial roadmaps.",
    "Personally designed early hardware iterations and software prototypes before they moved into production builds.",
    "Built an early computer vision MVP using OpenCV, a 3D camera and embedded systems for industrial human detection and safety.",
    "Built the business case and cost model, secured the initial development budget from executive sponsors, then used post-launch adoption and revenue results to secure follow-on budgets.",
    "Ran the internal ERP rollout: ERP integrated with the company CRM and Vanguard+ mobile app, data migration, process changeover and training delivered personally.",
  ];
  vanguardBullets.forEach(b => children.push(bulletWithPatentLink(b)));

  // 3. TurboApply Agency
  children.push(roleHead("Freelancer & Delivery Lead", "May 2026 to Present"));
  children.push(orgLine([
    orgLink("TurboApply Agency", "https://turboapply.agency/"),
    sepRun(ORG_SZ), orgBold("Batumi, Georgia"), sepRun(ORG_SZ), orgBold("Remote"),
  ]));
  const agencyBullets = Array.isArray(roles.turboapply_agency) && roles.turboapply_agency.length > 0 ? roles.turboapply_agency : [
    "Founded and operates TurboApply Agency, an AI automation and web systems company serving health services, professional services and small business operations.",
    "Designed and deployed custom AI receptionist agents handling lead qualification, appointment booking, CRM updates and after-hours inquiries.",
    "Built end-to-end systems combining conversion-focused websites, AI workflows, CRM and booking integrations, and outreach automation focused on turning leads into booked revenue.",
    "Runs discovery interviews and process mapping with clients, then converts target workflows into agent instructions, tool definitions and acceptance criteria.",
  ];
  agencyBullets.forEach(b => children.push(bulletWithPatentLink(b)));

  // 4. TurboApply.ai
  children.push(roleHead("Partner & Product Owner, Board", "May 2024 to Jan 2026"));
  children.push(orgLine([
    orgBold("TurboApply.ai"), sepRun(ORG_SZ), orgBold("Remote"), sepRun(ORG_SZ), orgBold("HR and recruiting technology"),
  ]));
  const turboAiBullets = Array.isArray(roles.turboapply_ai) && roles.turboapply_ai.length > 0 ? roles.turboapply_ai : [
    "Partner and Product Owner for an AI-powered job application and outreach platform built by a fully distributed team across UI/UX, browser extension, front end, back end and tech lead.",
    "Defined technical requirements and product specifications, managed cross-functional delivery, and drove business development and early go-to-market initiatives.",
    "Owned requirements for LLM-driven autofill and matching against a structured knowledge base, using curated reference data to drive validated output.",
  ];
  turboAiBullets.forEach(b => children.push(bulletWithPatentLink(b)));

  // 5. Vanguard Systems Co-op
  children.push(roleHead("R&D Engineering, Co-op", "Sep 2018 to Aug 2019"));
  children.push(orgLine([
    orgLink("Vanguard Systems", "https://www.vanguardsystems.com/"), sepRun(ORG_SZ), orgBold("Vancouver, Canada"), sepRun(ORG_SZ), orgBold("Full Time"),
  ]));
  const coopBullets = Array.isArray(roles.vanguard_coop) && roles.vanguard_coop.length > 0 ? roles.vanguard_coop : [
    "Developed an MVP for a human detector using OpenCV, a 3D camera and embedded systems to improve safety in industrial settings.",
  ];
  coopBullets.forEach(b => children.push(bulletWithPatentLink(b)));

  // 6. BCIT Board of Governors
  children.push(roleHead("Elected Director, Board of Governors", "Jun 2017 to May 2020"));
  children.push(orgLine([
    orgLink("British Columbia Institute of Technology", "https://www.bcit.ca/"), sepRun(ORG_SZ), orgBold("Vancouver, Canada"), sepRun(ORG_SZ), orgBold("Board"),
  ]));
  const bcitBullets = Array.isArray(roles.bcit_board) && roles.bcit_board.length > 0 ? roles.bcit_board : [
    "Served as a three-term elected student representative on the Institute Board.",
    "Liaised directly with provincial and federal government officials, contributing to policy development and governance.",
    "Networked with chairs and CEOs of various companies to adopt best practices in corporate governance.",
  ];
  bcitBullets.forEach(b => children.push(bulletWithPatentLink(b)));

  // ---------- EDUCATION ----------
  children.push(sectionHeading("Education", "🎓"));
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
  const skillsList = Array.isArray(payload.skills) && payload.skills.length > 0 ? payload.skills : [
    { label: "Tools:", items: "Jira, Confluence, Wrike, Miro, Figma, GitHub, Salesforce, Excel, PowerPoint, Claude, Hermes, OpenAI." },
    { label: "Product & Leadership:", items: "Product Ownership, Product Management, Business Development, R&D, Roadmapping, Cross-functional Team Leadership, Stakeholder Management, Go-to-Market, Product Launch, Customer Success, B2B, SaaS, Patenting." },
    { label: "AI & Automation:", items: "AI Agents, Workflow Automation, Generative AI Integrations, AI Receptionist, Conversational Systems, Prompt Systems, System Design for AI Products, Hermes Agents, Claude, Codex, OpenRouter, Spec Driven Development, MCP Servers, Prompt Engineering." },
    { label: "Technical:", items: "AWS, React Native, JavaScript, IoT Systems, Hardware-Firmware Integration, OpenCV, full-stack prototyping, Python, C, C++, Java, Android, REST APIs and webhooks." },
    { label: "Languages:", items: "English (fluent, professional proficiency), Russian (native), Ukrainian (fluent)." },
  ];
  skillsList.forEach(row => {
    if (row && row.label && row.items) {
      children.push(skillsRow(row.label, row.items));
    }
  });
  children.push(skillsRunsRow("Status:", [
    t("Canadian Citizen "), emoji("🇨🇦"), sepRun(),
    t("NEXUS card holder "), emoji("🇺🇸"), sepRun(),
    t("Based in Batumi, Georgia (UTC+4) "), emoji("🇬🇪"), sepRun(),
    t("Full-time remote, able to travel visa-free to EU "), emoji("🇪🇺"), t("."),
  ]));

  return new Document({
    creator: "Alex Mercer",
    title: `Alex Mercer Resume - ${payload.company || "Application"}`,
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
}

function letterBody(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    spacing: { after: 140, line: 275, lineRule: LineRuleType.EXACT },
    children: [new TextRun({ text: String(text || ""), font: FONT, size: BODY_SZ, color: TEXT })],
  });
}

function buildCoverLetterDoc(payload) {
  const tagline = payload.tagline || "Software Product Manager | AI Automation & Applied AI";
  const cl = payload.cover_letter || {};
  const children = [buildHeaderTable(tagline, 80)];

  // Rule under the header, matching the resume's section-rule treatment
  children.push(new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, space: 2, color: "C3CEDB" } },
    spacing: { before: 160, after: 200, line: 120, lineRule: LineRuleType.EXACT },
    children: [new TextRun({ text: "", font: FONT, size: 2 })],
  }));

  if (cl.addressee_company) {
    children.push(new Paragraph({
      spacing: { after: 30, line: 260, lineRule: LineRuleType.EXACT },
      children: [new TextRun({ text: cl.addressee_company, font: FONT, size: BODY_SZ, color: CONTACT })],
    }));
  }
  children.push(new Paragraph({
    spacing: { after: 30, line: 260, lineRule: LineRuleType.EXACT },
    children: [new TextRun({ text: cl.addressee_team || "Hiring Team", font: FONT, size: BODY_SZ, color: CONTACT })],
  }));
  children.push(new Paragraph({
    spacing: { after: 180, line: 260, lineRule: LineRuleType.EXACT },
    children: [new TextRun({ text: cl.re_line || `Re: ${payload.role || "Product Manager"}`, bold: true, font: FONT, size: BODY_SZ, color: NAVY })],
  }));

  children.push(new Paragraph({
    spacing: { after: 140, line: 275, lineRule: LineRuleType.EXACT },
    children: [new TextRun({ text: cl.salutation || `Dear ${payload.company || ""} Hiring Team,`.replace(/\s+/g, " "), font: FONT, size: BODY_SZ, color: TEXT })],
  }));

  const paras = Array.isArray(cl.paragraphs) && cl.paragraphs.length > 0 ? cl.paragraphs : [
    "I am a Software Product Manager with 7+ years shipping technical products across IoT, automation and applied AI. My strongest fit is for roles where the product has to turn ambiguous workflows into usable systems: requirements, cross-functional delivery, stakeholder translation, launch, measurement and iteration.",
    "At Apex Industrial, I led a 14-person multidisciplinary team across software, hardware, firmware and UI/UX, coordinating digital and IoT product work across 12 departments without direct managerial authority. I owned requirements, prioritization, rollout and executive communication, while keeping the technical constraints readable for business stakeholders and the business goals clear for engineers.",
    "Before that, I launched Vanguard+, an IoT product combining a sensor device, mobile application and web portal, and I am a named inventor on patent-pending WO2023212799. The product connected hardware, software, supply chain and business case work, serving a customer base of around 10,000 and supporting new revenue streams through the device, subscription and in-app parts ordering.",
    "More recently, I have been building AI automation systems through TurboApply Agency and TurboApply.ai: AI receptionist agents, workflow automation, CRM and booking integrations, LLM-driven autofill, structured knowledge bases and conversion-focused web systems. I bring both product judgment and hands-on technical depth to work effectively with engineering teams on applied AI products.",
    "I would welcome a conversation about how my product management, IoT and AI automation background could help your team ship reliable systems faster.",
  ];
  paras.forEach(p => {
    if (String(p || "").trim()) {
      children.push(letterBody(String(p).trim()));
    }
  });

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

  return new Document({
    creator: "Alex Mercer",
    title: `Alex Mercer Cover Letter - ${payload.company || "Application"}`,
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
}

async function main() {
  const inputJsonPath = process.argv[2];
  if (!inputJsonPath || !fs.existsSync(inputJsonPath)) {
    console.error("Usage: node build_vb_documents.js <payload.json>");
    process.exit(1);
  }
  const payload = JSON.parse(fs.readFileSync(inputJsonPath, "utf8"));
  if (payload.resume_docx_path) {
    const resumeDoc = buildResumeDoc(payload);
    const resumeBuf = await Packer.toBuffer(resumeDoc);
    fs.writeFileSync(payload.resume_docx_path, resumeBuf);
  }
  if (payload.cover_letter_docx_path) {
    const letterDoc = buildCoverLetterDoc(payload);
    const letterBuf = await Packer.toBuffer(letterDoc);
    fs.writeFileSync(payload.cover_letter_docx_path, letterBuf);
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
