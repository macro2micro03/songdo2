/* PRD (Word .docx) generator — 자재 반출입 관리(Material Gate Tool) */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, TableOfContents, HeadingLevel,
  BorderStyle, WidthType, ShadingType, VerticalAlign, PageNumber, PageBreak,
} = require("docx");

const FONT = "맑은 고딕";
const CW = 9026;            // A4 content width (1" margins)
const NAVY = "1F3864";
const HEAD_FILL = "D9E2F3";
const ZEBRA = "F2F5FB";
const BORDER = { style: BorderStyle.SINGLE, size: 1, color: "B7C3D9" };
const BORDERS = { top: BORDER, bottom: BORDER, left: BORDER, right: BORDER };

// ── helpers ────────────────────────────────────────────────────────────────
const run = (t, o = {}) => new TextRun({ text: t, font: FONT, ...o });
const P = (t, o = {}) => new Paragraph({ children: Array.isArray(t) ? t : [run(t, o.runOpts || {})],
  spacing: { after: o.after ?? 120, line: 276, ...(o.spacing || {}) }, ...o.p });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [run(t, { bold: true, color: NAVY, size: 30 })],
  spacing: { before: 280, after: 160 } });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [run(t, { bold: true, color: NAVY, size: 25 })],
  spacing: { before: 220, after: 120 } });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [run(t, { bold: true, color: "2E4B7A", size: 22 })],
  spacing: { before: 160, after: 90 } });
const bullet = (t, lvl = 0) => new Paragraph({ numbering: { reference: "bul", level: lvl },
  children: Array.isArray(t) ? t : [run(t)], spacing: { after: 60, line: 270 } });
const numbered = (t) => new Paragraph({ numbering: { reference: "num", level: 0 },
  children: Array.isArray(t) ? t : [run(t)], spacing: { after: 60, line: 270 } });

function cell(text, { w, head = false, fill, bold = false, align } = {}) {
  const kids = (Array.isArray(text) ? text : String(text).split("\n")).map((line) =>
    new Paragraph({
      alignment: align,
      spacing: { after: 0, line: 264 },
      children: line instanceof TextRun ? [line] : [run(String(line), { bold: bold || head, size: 19, color: head ? NAVY : "1A1A1A" })],
    }));
  return new TableCell({
    width: { size: w, type: WidthType.DXA }, borders: BORDERS, verticalAlign: VerticalAlign.CENTER,
    shading: { type: ShadingType.CLEAR, fill: head ? HEAD_FILL : (fill || "FFFFFF") },
    margins: { top: 60, bottom: 60, left: 110, right: 110 },
    children: kids,
  });
}

function table(headers, rows, widths) {
  const headRow = new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, { w: widths[i], head: true })) });
  const bodyRows = rows.map((r, ri) => new TableRow({
    children: r.map((c, i) => cell(c, { w: widths[i], fill: ri % 2 ? ZEBRA : "FFFFFF" })),
  }));
  return new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: widths, rows: [headRow, ...bodyRows] });
}
const spacer = (h = 80) => new Paragraph({ spacing: { after: h }, children: [run("")] });

// ── content ──────────────────────────────────────────────────────────────
const children = [];

// Cover
children.push(
  new Paragraph({ spacing: { before: 1800, after: 0 }, alignment: AlignmentType.CENTER,
    children: [run("제품 요구사항 정의서 (PRD)", { bold: true, size: 52, color: NAVY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 0 },
    children: [run("자재 반출입 관리 시스템", { bold: true, size: 36, color: "2E4B7A" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 0 },
    children: [run("Material Gate Tool · 송도역세권아파트 2BL", { size: 24, color: "555555" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 900, after: 0 },
    children: [run("버전 3.0.0", { size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 0 },
    children: [run("작성일 2026-06-11", { size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 0 },
    children: [run("문서 상태 : 작성본 (Draft)", { size: 22, color: "555555" })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

// TOC
children.push(
  new Paragraph({ children: [run("목차", { bold: true, size: 30, color: NAVY })], spacing: { after: 160 } }),
  new TableOfContents("목차", { hyperlink: true, headingStyleRange: "1-3" }),
  new Paragraph({ children: [new PageBreak()] }),
);

// 1. 개요
children.push(H1("1. 개요"));
children.push(H2("1.1 제품 정의"));
children.push(P("건설현장(송도역세권아파트 2BL)의 자재 반출입을 사전 신청–계획 확정(서명)–현장 실행(사진·체크리스트)–산출물(PDF) 흐름으로 관리하는 운영형 시스템이다. 협력사와 현장 관리자가 자재의 반입/반출 일정, 하역 위치·시간대, 지하 터미널 저장 위치를 통제하고, 점유 충돌을 방지하며, 승인 기록과 산출물을 표준화한다."));
children.push(H2("1.2 배경 및 해결 과제"));
children.push(bullet("종이/구두 기반 반출입 신청으로 인한 일정 충돌, 터미널 중복 점유, 책임 소재 불명확."));
children.push(bullet("하역 구역·시간대와 지하 저장 터미널이 분리 관리되지 않아 현장 혼선 발생."));
children.push(bullet("승인·서명·실행 증빙이 흩어져 산출물(반출입 계획서/허가서) 작성에 수작업 소요."));
children.push(bullet("데스크톱(관리자)과 현장 모바일(협력사·경비) 사용 환경이 달라 단일 화면으로는 부적합."));
children.push(H2("1.3 목표 및 성공 지표"));
children.push(table(
  ["목표", "설명", "성공 지표(예시)"],
  [
    ["일정·위치 충돌 제거", "하역 시간대 및 터미널 저장 점유를 실시간 가시화·차단", "중복 점유 신청 0건"],
    ["승인 표준화", "구분별 라우팅(반입/반출)·서명으로 계획 확정", "승인 누락/역추적 불가 건 0"],
    ["증빙 자동화", "사진·체크리스트 기반 PDF 산출물 자동 생성", "산출물 수작업 시간 80% 감소"],
    ["현장 접근성", "모바일 PWA로 현장에서 신청·확인", "모바일 사용 비중 50%+"],
  ],
  [2200, 4626, 2200],
));

// 2. 사용자 및 역할
children.push(H1("2. 사용자 및 역할"));
children.push(P("계정은 프로젝트(현장) 단위로 분리되며(project_id 멀티테넌시), 로그인은 아이디/비밀번호 기반이다. 역할(role)과 권한(권한 플래그)은 분리되어 운영된다."));
children.push(H2("2.1 역할(Role)"));
children.push(table(
  ["역할", "주 사용자", "주요 행위"],
  [
    ["삼성물산", "원청 현장 관리자", "신청 검토·계획 확정(서명), 터미널 위치/기간 배정, 관리자 설정"],
    ["협력사", "협력업체 담당자", "반출입 신청 등록, 본인 신청 현황·확정 대기 확인, 사진 업로드"],
  ],
  [2200, 3200, 3626],
));
children.push(H2("2.2 권한(Permission)"));
children.push(table(
  ["권한", "근거 필드", "설명"],
  [
    ["관리자", "profiles.is_admin", "관리자 설정·서명 라우팅·터미널/존·보관일수·조기 해제 등 운영 권한"],
    ["시스템관리자", "profiles.is_sysadmin", "DB로만 부여되는 최상위 권한(계정/권한 관리). 화면에서 변경 불가"],
  ],
  [2200, 2600, 4226],
));

// 3. 시스템 아키텍처
children.push(H1("3. 시스템 아키텍처"));
children.push(H2("3.1 구성"));
children.push(P([run("두 개의 프런트엔드 앱이 ", {}), run("하나의 Supabase 백엔드", { bold: true }), run("를 공유한다.", {})]));
children.push(table(
  ["구성요소", "기술", "용도"],
  [
    ["데스크톱 앱", "Streamlit (Python)", "관리자·담당자용 전체 기능(계획 확정·관리·산출물·대시보드)"],
    ["모바일 앱", "Next.js 16 (App Router, React 19, Tailwind)", "현장용 경량 기능(로그인·홈·원장·승인·사진·신청)"],
    ["백엔드", "Supabase (Postgres 17 + Auth + Storage)", "단일 정본 DB·인증·파일 저장 (ap-northeast-2)"],
    ["저장소", "Storage 버킷 2종", "photos(공개·사진), material-gate(비공개·PDF/QR/서명)"],
  ],
  [2000, 3526, 3500],
));
children.push(H2("3.2 인증 및 보안"));
children.push(bullet("하이브리드 인증: 신규 계정은 PBKDF2 해시(profiles.password_hash/salt), 기존 계정은 Supabase Auth 폴백(supabase_uid)."));
children.push(bullet("비밀번호 재설정: Supabase Auth 이메일 OTP(8자리) 기반. 비밀번호 최소 6자."));
children.push(bullet("멀티테넌시: 모든 테이블 project_id 기준 분리. 전 public 테이블 RLS 활성(anon/authenticated 정책)."));
children.push(bullet("권한 모델: is_admin(운영)·is_sysadmin(DB 전용)으로 분리. 시스템관리자 권한은 화면에서 변경 불가."));
children.push(H2("3.3 배포"));
children.push(table(
  ["대상", "경로", "비고"],
  [
    ["Streamlit Cloud", "songdo2-ino.streamlit.app", "GitHub 260423-MPM master 추적, push 시 자동 배포"],
    ["브랜치 전략", "master(개발) / release(공유) / v1.0.0(태그)", "공유본은 release 브랜치로 fast-forward 반영"],
    ["모바일", "Vercel (예정)", "songdo2-mobile, 독립 저장소"],
  ],
  [2200, 3826, 3000],
));

// 4. 워크플로우
children.push(H1("4. 핵심 워크플로우"));
children.push(P("스케줄/신청 → 계획 확정(서명) → 실행(사진+체크리스트) → 산출물(PDF) → 공유."));
children.push(H2("4.1 상태 머신"));
children.push(table(
  ["대상", "상태 전이"],
  [
    ["요청(requests)", "PENDING_APPROVAL → APPROVED / REJECTED → EXECUTING → DONE"],
    ["승인(approvals)", "PENDING → APPROVED / REJECTED"],
  ],
  [2400, 6626],
));
children.push(H2("4.2 승인 라우팅"));
children.push(P([run("구분(반입/반출)별 승인 단계는 settings.approval_routing_json 으로 구성한다. 예: ", {}),
  run('{"IN": ["공사"], "OUT": ["안전","공사"]}', { font: "Consolas", size: 19 }), run(".", {})]));

// 5. 기능 요구사항
children.push(H1("5. 기능 요구사항 (모듈별)"));
children.push(P("모듈은 프로젝트별로 활성/비활성(project_modules) 및 관리자/사용자 노출(enabled_admin/enabled_user)을 제어한다."));

children.push(H2("5.1 신청 · 스케줄 (schedule)"));
children.push(bullet("날짜별 타임라인에서 반입/반출 신청 등록 — 회사·자재·차량·시간대·하역존·터미널 입력."));
children.push(bullet("30분 단위 슬롯(06:00~18:00)로 시간대 선택, 예약존(booking_zones)·터미널존(terminal_zones) 설정 기반."));
children.push(bullet([run("터미널 점유 현황 카드(B1F/B2F): ", {}), run("다중일 점유", { bold: true }),
  run(" 기준으로 반입일~기본 보관일수 동안 점유된 터미널을 🟡/🔴로 표시하고 신청 드롭다운에서 제외(차단).", {})]));
children.push(bullet("점유 터미널 클릭 시 보관 업체·자재·기간 안내. 관리자에게는 ‘보관 종료(해제)’ 버튼 제공."));

children.push(H2("5.2 계획 확정 (approval)"));
children.push(bullet("구분별 라우팅에 따라 담당 역할이 검토 후 ‘계획 확정’(서명). 서명은 이미지 또는 정자(이름 자동 기록) — settings.signature_enabled 토글."));
children.push(bullet("협력사 계정은 서명 권한이 없어 본인 신청의 확정 대기 현황만 조회."));
children.push(bullet("승인 화면 내 하역·저장 위치/현황 모듈을 통해 위치·기간을 확정(아래 5.3)."));

children.push(H2("5.3 하역 · 저장 위치 / 현황 (핵심)"));
children.push(H3("5.3.1 하역(지상)"));
children.push(bullet("지상 하역존(A~G) 선택 + 30분 슬롯 타임테이블."));
children.push(bullet("오전(06:00~12:00)·오후(12:00~18:00) 좌우 2열 타임라인(모바일도 2열 유지). 클릭으로 연속 시간대 선택."));
children.push(bullet("같은 날짜·하역존·구분에 점유된 슬롯은 빨강으로 표시(클릭 불가), 클릭 시 팝오버로 점유 시간대·업체·자재·신청자 표시."));
children.push(H3("5.3.2 저장(지하 터미널)"));
children.push(bullet("지하 터미널(B1·B2-01~13) 선택. 신청 시 입력한 터미널(gate) 기본값, 저장 배정(store_terminal) 우선."));
children.push(bullet([run("저장 기간 자동 산정: ", {}), run("반입일 ~ 기본 보관일수(기본 14일)", { bold: true }),
  run(". 시작일/종료일 수동 입력은 제거되고 읽기전용 캡션으로 표시.", {})]));
children.push(bullet("터미널은 1자재 배타 점유. B1F/B2F 점유 현황 그리드(빨강=점유, 초록=빈곳) + 도면 보기(지상/B1F/B2F)."));
children.push(bullet("충돌 검사: 선택 터미널이 해당 기간에 이미 점유 중이면 저장 차단."));
children.push(bullet("조기 해제(관리자): 자재가 빠지면 ‘보관 종료(해제)’로 store_released 처리 → 모든 화면에서 점유 즉시 해제."));

children.push(H2("5.4 실행 (execution)"));
children.push(bullet("필수 사진 3종(상차 전/상차 후/하역·통제구간) 촬영·업로드(photos 버킷)."));
children.push(bullet("체크리스트(차량번호·신분증·PPE·덮개·제동·소화기 등 10항목) 확인 후 실행 완료."));

children.push(H2("5.5 산출물 (outputs)"));
children.push(bullet("계획서·허가서·체크리스트·실행·번들 PDF 생성 후 material-gate(비공개) 버킷 저장."));
children.push(bullet("계획서 PDF에 하역존·저장 터미널·저장 기간·서명(이미지 또는 정자) 포함."));
children.push(bullet("한글 렌더링: NanumGothic 폰트 번들. 폰트 미등록 시 관리자 헤더에 자동 진단 노출."));

children.push(H2("5.6 원장 (ledger)"));
children.push(bullet("전체 반출입 대장 조회 — 신청자(이름/직책 + 로그인 ID), 회사·자재·구분·일시·위치·상태 표시."));

children.push(H2("5.7 대시보드 (dashboard)"));
children.push(bullet("일별 KPI 집계(반입/반출 건수·상태 등). KPI 캐시(30초)·조회 한도로 성능 최적화."));

children.push(H2("5.8 관리자 (admin)"));
children.push(table(
  ["설정", "settings 키", "설명"],
  [
    ["승인 라우팅", "approval_routing_json", "구분별 승인 단계 역할 구성"],
    ["예약존/게이트존", "booking_zones_json, gate_zones_json", "신청 시간대 구역·게이트 구역 관리"],
    ["터미널 사용 존", "terminal_zones_json", "터미널 드롭다운을 노출할 예약존 지정"],
    ["기본 보관일수", "storage_default_days", "터미널 점유 기본 기간(기본 14일, 1~180)"],
    ["승인 서명 사용", "signature_enabled", "끄면 서명 입력 제거·이름 정자 자동 기록"],
    ["현장명/핀", "site_name, site_pin, admin_pin", "현장 기본 정보 및 접근 핀"],
  ],
  [2200, 3526, 3300],
));
children.push(P("그 외 기능 모듈 노출 설정(모듈별 활성/관리자·사용자 표시), 사용자·권한 관리 제공."));

children.push(H2("5.9 모바일 앱 (Next.js)"));
children.push(bullet("대시보드를 제외한 현장 핵심 기능: 로그인(ID/PW)·홈·원장·승인·사진·신규 신청(슬롯 선택기)."));
children.push(bullet("@supabase/ssr 기반 세션, proxy.ts 미들웨어. 동일 Supabase 백엔드·RPC 공유."));

// 6. 데이터 모델
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(H1("6. 데이터 모델 (Supabase Postgres)"));
children.push(P("project_id 멀티테넌시. 주요 테이블 및 핵심 컬럼은 다음과 같다."));
children.push(table(
  ["테이블", "용도", "핵심 컬럼"],
  [
    ["profiles", "계정/권한", "username, name, role, is_admin, is_sysadmin, email, company_name, password_hash, salt, supabase_uid"],
    ["projects", "현장(테넌트)", "id, name, site_pin, admin_pin"],
    ["project_modules", "모듈 노출", "module_key, enabled, enabled_admin, enabled_user, sort_order"],
    ["requests", "반출입 요청", "kind, status, company_name, item_name, date, time_from/to, gate, booking_zone, loading_method, store_terminal, store_start, store_end, store_released, requester_name/role/username"],
    ["approvals", "승인 단계", "req_id, step_no, role_required, status, signer_name, sign_png_path, signed_at, reject_reason"],
    ["executions", "실행 결과", "req_id, executed_by, check_json, required_photo_ok"],
    ["photos", "사진", "req_id, slot_key, label, file_path, storage_url"],
    ["outputs", "산출물", "req_id, plan_pdf_path, permit_pdf_path, check_pdf_path, exec_pdf_path, bundle_pdf_path, qr_png_path"],
    ["schedules", "스케줄", "req_id, schedule_date, time_from/to, kind, gate, booking_zone, status, color"],
    ["terminal_releases", "당일 해제", "terminal, release_date (당일 표시용 해제 기록)"],
    ["settings", "전역 설정", "key, value (현장 운영 파라미터)"],
  ],
  [1700, 1700, 5626],
));
children.push(P("주: 다중일 터미널 점유는 requests의 store_terminal/store_start/store_end/store_released(미설정 시 반입일~기본 보관일수) 및 gate(반입일 기준)로 산정한다. terminal_releases는 신청 화면 당일 표시용이며, 다중일 점유 해제는 store_released로 처리한다."));

// 7. 비기능 요구사항
children.push(H1("7. 비기능 요구사항"));
children.push(H2("7.1 모바일 반응형 (현장 우선)"));
children.push(table(
  ["구분", "범위", "컬럼 동작"],
  [
    ["스마트폰", "≤ 480px", "st.columns → 1열 스택(전용 예외 컴포넌트는 유지)"],
    ["태블릿", "481~768px", "4열 → 2열"],
    ["데스크톱", "≥ 769px", "원래 레이아웃 유지"],
  ],
  [2200, 2400, 4426],
));
children.push(bullet("터치 타겟 min-height 44px, 입력 폰트 16px(iOS 자동 줌 방지), 제출 버튼 52px."));
children.push(bullet("가로 스크롤 금지, 긴 텍스트 줄바꿈, 고정 px 폭 금지(%, min/max, clamp 사용)."));
children.push(H2("7.2 PWA · 성능 · 한글"));
children.push(bullet("PWA: ‘송도2-INO’로 설치 가능(정적 manifest, 절대 경로 아이콘)."));
children.push(bullet("성능: KPI 캐시(30초), 타깃 캐시 무효화, 조회 한도, 스피너."));
children.push(bullet("한글 PDF: NanumGothic 번들로 □ 깨짐 방지, 폰트 파일 크기 검증."));

// 8. 범위 외 / 향후
children.push(H1("8. 범위 외 및 향후 과제"));
children.push(bullet("건별 보관기간 직접 조정 UI(현재는 자동 산정 + 조기 해제로 운영)."));
children.push(bullet("반입↔반출 자동 연계(현재 반출은 별개 요청, 터미널 점유는 반입 기준)."));
children.push(bullet("RLS 정책 세분화(현재 광역 정책에서 역할 기반 강화 예정)."));
children.push(bullet("모바일 앱 Vercel 정식 배포 및 상태 라벨(‘확정’) 용어 통일."));

children.push(spacer(40));
children.push(P([run("본 문서는 현재 구현 상태(v3.0.0)를 기준으로 작성된 작성본이며, 변경 시 개정 이력으로 관리한다.", { italics: true, color: "555555", size: 19 })]));

// ── document ───────────────────────────────────────────────────────────────
const doc = new Document({
  creator: "자재 반출입 관리",
  title: "PRD — 자재 반출입 관리 시스템",
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: FONT, color: NAVY }, paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 25, bold: true, font: FONT, color: NAVY }, paragraph: { spacing: { before: 220, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: FONT, color: "2E4B7A" }, paragraph: { spacing: { before: 160, after: 90 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bul", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1080, hanging: 270 } } } },
      ]},
      { reference: "num", levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } },
      ]},
    ],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    headers: { default: new Header({ children: [ new Paragraph({
      alignment: AlignmentType.RIGHT, spacing: { after: 0 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 6 } },
      children: [run("자재 반출입 관리 시스템 — PRD v3.0.0", { size: 16, color: "777777" })] }) ] }) },
    footers: { default: new Footer({ children: [ new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 0 },
      children: [run("", { size: 16 }), new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: "777777" })] }) ] }) },
    children,
  }],
});

const out = path.join(__dirname, "PRD_자재반출입관리.docx");
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(out, buf); console.log("WROTE", out, buf.length, "bytes"); });
