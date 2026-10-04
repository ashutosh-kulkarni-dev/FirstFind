/* @ds-bundle: {"format":3,"namespace":"HelpDeskDesignSystem_60f508","components":[{"name":"Button","sourcePath":"components/buttons/Button.jsx"},{"name":"ChoiceButtons","sourcePath":"components/buttons/ChoiceButtons.jsx"},{"name":"OptionButton","sourcePath":"components/buttons/OptionButton.jsx"},{"name":"ChatBubble","sourcePath":"components/chat/ChatBubble.jsx"},{"name":"TypingIndicator","sourcePath":"components/chat/ChatBubble.jsx"},{"name":"ThreadMessage","sourcePath":"components/chat/ThreadMessage.jsx"},{"name":"KpiCard","sourcePath":"components/data/KpiCard.jsx"},{"name":"Badge","sourcePath":"components/feedback/Badge.jsx"},{"name":"Skeleton","sourcePath":"components/feedback/Skeleton.jsx"},{"name":"SkeletonGroup","sourcePath":"components/feedback/Skeleton.jsx"},{"name":"StarRating","sourcePath":"components/feedback/StarRating.jsx"},{"name":"StatusBadge","sourcePath":"components/feedback/StatusBadge.jsx"},{"name":"Toast","sourcePath":"components/feedback/Toast.jsx"},{"name":"ChoiceTile","sourcePath":"components/forms/ChoiceTile.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Textarea","sourcePath":"components/forms/Textarea.jsx"},{"name":"Tabs","sourcePath":"components/navigation/Tabs.jsx"},{"name":"Modal","sourcePath":"components/overlay/Modal.jsx"}],"sourceHashes":{"components/buttons/Button.jsx":"438b8249c0c1","components/buttons/ChoiceButtons.jsx":"e0ac9c928932","components/buttons/OptionButton.jsx":"b44cac330bae","components/chat/ChatBubble.jsx":"388eefd7b9f1","components/chat/ThreadMessage.jsx":"3c9d7782f40b","components/data/KpiCard.jsx":"54c77e3f8cfd","components/feedback/Badge.jsx":"25d666e09b04","components/feedback/Skeleton.jsx":"80cbf88d4ea2","components/feedback/StarRating.jsx":"41352c6cad91","components/feedback/StatusBadge.jsx":"f340d67e4a01","components/feedback/Toast.jsx":"08b60cca847c","components/forms/ChoiceTile.jsx":"7af58e80bf5e","components/forms/Input.jsx":"c0e52dd867cd","components/forms/Select.jsx":"24ab9dd768ee","components/forms/Textarea.jsx":"65b4664c1ad1","components/navigation/Tabs.jsx":"411101582f4c","components/overlay/Modal.jsx":"8fe22d95b471","ui_kits/admin/AdminApp.jsx":"cf2d507a5275","ui_kits/admin/data.js":"2eae30de1899","ui_kits/student/StudentApp.jsx":"7efb37092334","ui_kits/student/data.js":"4ecddbf0eb55"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.HelpDeskDesignSystem_60f508 = window.HelpDeskDesignSystem_60f508 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/buttons/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Button — the Help Desk primary action button.
 * Theme-aware: reads --accent, so it renders blue in the student portal
 * and purple inside an .admin-portal scope. Matches the product's solid
 * and outline button families.
 */
function Button({
  variant = 'primary',
  size = 'md',
  block = false,
  disabled = false,
  type = 'button',
  className = '',
  children,
  ...rest
}) {
  const cls = ['hd-btn', `hd-btn--${variant}`, `hd-btn--${size}`, block ? 'hd-btn--block' : '', className].filter(Boolean).join(' ');
  return /*#__PURE__*/React.createElement("button", _extends({
    type: type,
    className: cls,
    disabled: disabled
  }, rest), children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/buttons/Button.jsx", error: String((e && e.message) || e) }); }

// components/buttons/ChoiceButtons.jsx
try { (() => {
/**
 * ChoiceButtons — the Yes/No (green/red) decision pair used at chat
 * confirmation points (e.g. "Submit this ticket?").
 */
function ChoiceButtons({
  yesLabel = "Yes, that's right",
  noLabel = 'No, go back',
  onYes,
  onNo,
  disabled = false
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "yesno-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: "yn-btn yes",
    onClick: onYes,
    disabled: disabled
  }, yesLabel), /*#__PURE__*/React.createElement("button", {
    className: "yn-btn no",
    onClick: onNo,
    disabled: disabled
  }, noLabel));
}
Object.assign(__ds_scope, { ChoiceButtons });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/buttons/ChoiceButtons.jsx", error: String((e && e.message) || e) }); }

// components/buttons/OptionButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * OptionButton — a full-width selectable row used in the chat decision tree.
 * Left-aligned label with a chevron that nudges right on hover.
 */
function OptionButton({
  label,
  children,
  disabled = false,
  className = '',
  ...rest
}) {
  return /*#__PURE__*/React.createElement("button", _extends({
    className: `opt-btn ${className}`.trim(),
    disabled: disabled
  }, rest), /*#__PURE__*/React.createElement("span", null, label ?? children), /*#__PURE__*/React.createElement("span", {
    className: "arrow"
  }, "\u203A"));
}
Object.assign(__ds_scope, { OptionButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/buttons/OptionButton.jsx", error: String((e && e.message) || e) }); }

// components/chat/ChatBubble.jsx
try { (() => {
/**
 * ChatBubble — a labelled message in the main guided-chat column.
 * from="support" renders a left, white bubble under a "Support" label;
 * from="user" renders a right, blue bubble under a "You" label.
 */
function ChatBubble({
  from = 'support',
  label,
  children
}) {
  const isUser = from === 'user';
  return /*#__PURE__*/React.createElement("div", {
    className: "msg"
  }, /*#__PURE__*/React.createElement("div", {
    className: `msg-label ${isUser ? 'right' : ''}`
  }, label ?? (isUser ? 'You' : 'Support')), /*#__PURE__*/React.createElement("div", {
    className: `bubble ${isUser ? 'user' : ''}`
  }, children));
}

/** TypingIndicator — three bouncing dots shown while support is "typing". */
function TypingIndicator() {
  return /*#__PURE__*/React.createElement("div", {
    className: "typing-indicator"
  }, /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("span", null));
}
Object.assign(__ds_scope, { ChatBubble, TypingIndicator });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/chat/ChatBubble.jsx", error: String((e && e.message) || e) }); }

// components/chat/ThreadMessage.jsx
try { (() => {
/**
 * ThreadMessage — a compact ticket-thread bubble (student right/blue,
 * admin left/white) with a meta line. Used in the student ticket panel
 * and the admin expanded thread.
 */
function ThreadMessage({
  from = 'student',
  meta,
  children
}) {
  const isStudent = from === 'student';
  return /*#__PURE__*/React.createElement("div", {
    className: `msg-bubble ${isStudent ? 'student' : 'admin'}`
  }, children, meta && /*#__PURE__*/React.createElement("div", {
    className: "msg-meta"
  }, meta));
}
Object.assign(__ds_scope, { ThreadMessage });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/chat/ThreadMessage.jsx", error: String((e && e.message) || e) }); }

// components/data/KpiCard.jsx
try { (() => {
/**
 * KpiCard — a dashboard metric tile: uppercase label, large value, sub-text,
 * and a coloured left accent rail.
 */
function KpiCard({
  label,
  value,
  sub,
  accent = 'blue'
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: `dash-kpi-card accent-${accent}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "dash-kpi-label"
  }, label), /*#__PURE__*/React.createElement("div", {
    className: "dash-kpi-value"
  }, value), sub && /*#__PURE__*/React.createElement("div", {
    className: "dash-kpi-sub"
  }, sub));
}
Object.assign(__ds_scope, { KpiCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/KpiCard.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const TONES = {
  green: {
    color: 'var(--green)',
    bg: 'var(--green-lt)',
    bd: 'var(--green-bd)'
  },
  blue: {
    color: 'var(--blue)',
    bg: 'var(--blue-lt)',
    bd: 'var(--blue-bd)'
  },
  purple: {
    color: 'var(--purple)',
    bg: 'var(--purple-lt)',
    bd: 'var(--purple-bd)'
  },
  orange: {
    color: 'var(--orange)',
    bg: 'var(--orange-lt)',
    bd: 'var(--orange-bd)'
  },
  red: {
    color: 'var(--red)',
    bg: 'var(--red-lt)',
    bd: 'var(--red-bd)'
  },
  neutral: {
    color: 'var(--muted)',
    bg: 'var(--bg)',
    bd: 'var(--border)'
  }
};

/**
 * Badge — a small rounded pill for roles, counts and tags (e.g. "Student",
 * "Admin", "🔄 Reopenable"). For ticket lifecycle status use StatusBadge.
 */
function Badge({
  tone = 'neutral',
  children,
  className = '',
  ...rest
}) {
  const t = TONES[tone] || TONES.neutral;
  return /*#__PURE__*/React.createElement("span", _extends({
    className: className,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      fontSize: 'var(--fs-11)',
      fontWeight: 500,
      padding: '3px 10px',
      borderRadius: 'var(--r-pill)',
      border: `1px solid ${t.bd}`,
      color: t.color,
      background: t.bg,
      whiteSpace: 'nowrap'
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Badge.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Skeleton.jsx
try { (() => {
/**
 * Skeleton — shimmering loading placeholder. variant "line" for text rows,
 * "card" for list/thread item blocks.
 */
function Skeleton({
  variant = 'line',
  width,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: `skeleton skeleton-${variant}`,
    style: {
      ...(width ? {
        width
      } : {}),
      ...style
    }
  });
}

/** SkeletonGroup — the padded wrapper holding a set of skeletons. */
function SkeletonGroup({
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "skeleton-wrap"
  }, children);
}
Object.assign(__ds_scope, { Skeleton, SkeletonGroup });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Skeleton.jsx", error: String((e && e.message) || e) }); }

// components/feedback/StarRating.jsx
try { (() => {
const LABELS = ['Very bad', 'Bad', 'Okay', 'Good', 'Excellent'];

/**
 * StarRating — 1–5 star control. Interactive (hover + click) by default;
 * pass readOnly for a static display of an existing rating.
 */
function StarRating({
  value = 0,
  onChange,
  readOnly = false,
  showLabel = true,
  disabled = false
}) {
  const [hover, setHover] = React.useState(0);
  if (readOnly) {
    return /*#__PURE__*/React.createElement("span", {
      className: "star-display"
    }, [1, 2, 3, 4, 5].map(n => /*#__PURE__*/React.createElement("span", {
      key: n,
      className: `star ${n <= value ? 'filled' : ''}`
    }, "\u2605")));
  }
  const display = hover || value;
  return /*#__PURE__*/React.createElement("div", {
    className: "star-rating",
    role: "radiogroup",
    "aria-label": "Rating"
  }, [1, 2, 3, 4, 5].map(n => /*#__PURE__*/React.createElement("button", {
    key: n,
    type: "button",
    className: `star-btn ${n <= display ? 'filled' : ''}`,
    onClick: () => onChange?.(n),
    onMouseEnter: () => setHover(n),
    onMouseLeave: () => setHover(0),
    disabled: disabled,
    "aria-label": `${n} star${n > 1 ? 's' : ''}`
  }, "\u2605")), showLabel && display > 0 && /*#__PURE__*/React.createElement("span", {
    className: "star-label"
  }, LABELS[display - 1]));
}
Object.assign(__ds_scope, { StarRating });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/StarRating.jsx", error: String((e && e.message) || e) }); }

// components/feedback/StatusBadge.jsx
try { (() => {
function statusClass(status) {
  if (!status) return '';
  return String(status).toLowerCase().replace(/\s+/g, '-');
}

/**
 * StatusBadge — the canonical ticket-status pill. Maps any lifecycle status
 * string ("new issue", "In progress", "resolved", "closed", "Invalid",
 * "cancelled", "additional information requested/provided") to its colour.
 */
function StatusBadge({
  status
}) {
  return /*#__PURE__*/React.createElement("span", {
    className: `status-badge ${statusClass(status)}`
  }, status);
}
Object.assign(__ds_scope, { StatusBadge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/StatusBadge.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Toast.jsx
try { (() => {
const ICON = {
  success: '✓',
  error: '!',
  info: 'ℹ'
};

/**
 * Toast — a single dismissible notification. The product shows these
 * bottom-right; render inside a `.toast-host` fixed container.
 */
function Toast({
  type = 'info',
  message,
  onDismiss
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: `toast toast-${type}`,
    onClick: onDismiss,
    role: "status"
  }, /*#__PURE__*/React.createElement("span", {
    className: "toast-icon"
  }, ICON[type] || ICON.info), /*#__PURE__*/React.createElement("span", {
    className: "toast-msg"
  }, message), /*#__PURE__*/React.createElement("button", {
    className: "toast-close",
    onClick: onDismiss,
    "aria-label": "Dismiss"
  }, "\u2715"));
}
Object.assign(__ds_scope, { Toast });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Toast.jsx", error: String((e && e.message) || e) }); }

// components/forms/ChoiceTile.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * ChoiceTile — a bordered radio/checkbox row with a bold title and helper
 * text. Used in the node-behaviour picker and reopen-permission toggle.
 */
function ChoiceTile({
  type = 'radio',
  title,
  description,
  className = '',
  ...rest
}) {
  return /*#__PURE__*/React.createElement("label", {
    className: `hd-choice ${className}`.trim()
  }, /*#__PURE__*/React.createElement("input", _extends({
    type: type
  }, rest)), /*#__PURE__*/React.createElement("span", {
    className: "hd-choice-text"
  }, /*#__PURE__*/React.createElement("strong", null, title), description && /*#__PURE__*/React.createElement("span", null, description)));
}
Object.assign(__ds_scope, { ChoiceTile });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/ChoiceTile.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Input — labelled single-line text field. Uppercase label, accent focus ring
 * that follows the portal theme, optional inline error.
 */
function Input({
  label,
  error,
  id,
  className = '',
  ...rest
}) {
  const inputId = id || (label ? `in-${label.replace(/\s+/g, '-').toLowerCase()}` : undefined);
  const field = /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("input", _extends({
    id: inputId,
    className: `hd-input ${error ? 'hd-input--error' : ''} ${className}`.trim()
  }, rest)), error && /*#__PURE__*/React.createElement("span", {
    className: "hd-field-error"
  }, "\u26A0 ", error));
  if (!label) return field;
  return /*#__PURE__*/React.createElement("div", {
    className: "hd-field"
  }, /*#__PURE__*/React.createElement("label", {
    className: "hd-label",
    htmlFor: inputId
  }, label), field);
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Select — labelled dropdown with a custom chevron, theme-aware focus.
 * Pass options as [{value, label}] or use children <option>.
 */
function Select({
  label,
  options,
  id,
  className = '',
  children,
  ...rest
}) {
  const selId = id || (label ? `sel-${label.replace(/\s+/g, '-').toLowerCase()}` : undefined);
  const control = /*#__PURE__*/React.createElement("select", _extends({
    id: selId,
    className: `hd-select ${className}`.trim()
  }, rest), options ? options.map(o => /*#__PURE__*/React.createElement("option", {
    key: o.value,
    value: o.value
  }, o.label)) : children);
  if (!label) return control;
  return /*#__PURE__*/React.createElement("div", {
    className: "hd-field"
  }, /*#__PURE__*/React.createElement("label", {
    className: "hd-label",
    htmlFor: selId
  }, label), control);
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Textarea.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Textarea — labelled multi-line field with optional character counter
 * and inline error. Used for ticket descriptions, replies and remarks.
 */
function Textarea({
  label,
  error,
  id,
  maxLength,
  value,
  showCount = false,
  className = '',
  ...rest
}) {
  const taId = id || (label ? `ta-${label.replace(/\s+/g, '-').toLowerCase()}` : undefined);
  const len = typeof value === 'string' ? value.length : 0;
  const body = /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative'
    }
  }, /*#__PURE__*/React.createElement("textarea", _extends({
    id: taId,
    className: `hd-textarea ${error ? 'hd-textarea--error' : ''} ${className}`.trim(),
    maxLength: maxLength,
    value: value
  }, rest)), showCount && maxLength != null && /*#__PURE__*/React.createElement("span", {
    style: {
      position: 'absolute',
      bottom: 6,
      right: 10,
      fontSize: 11,
      pointerEvents: 'none',
      color: len >= maxLength ? 'var(--red)' : 'var(--muted)'
    }
  }, maxLength - len, "/", maxLength));
  return /*#__PURE__*/React.createElement("div", {
    className: label ? 'hd-field' : ''
  }, label && /*#__PURE__*/React.createElement("label", {
    className: "hd-label",
    htmlFor: taId
  }, label), body, error && /*#__PURE__*/React.createElement("span", {
    className: "hd-field-error"
  }, "\u26A0 ", error));
}
Object.assign(__ds_scope, { Textarea });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Textarea.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Tabs.jsx
try { (() => {
/**
 * Tabs — the admin underline tab bar. Pass tabs as [{id, label}]; the
 * active tab is underlined in purple.
 */
function Tabs({
  tabs = [],
  active,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "tab-bar"
  }, tabs.map(t => /*#__PURE__*/React.createElement("button", {
    key: t.id,
    className: `tab-btn ${active === t.id ? 'active' : ''}`,
    onClick: () => onChange?.(t.id)
  }, t.label)));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Tabs.jsx", error: String((e && e.message) || e) }); }

// components/overlay/Modal.jsx
try { (() => {
/**
 * Modal — centered dialog with scrim. Title + subtitle header and a
 * scrollable body. Click the backdrop to dismiss. Used for the admin
 * node editor and any confirm/edit dialog.
 */
function Modal({
  open = true,
  title,
  subtitle,
  onClose,
  children,
  footer
}) {
  if (!open) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "modal-overlay",
    onClick: e => e.target === e.currentTarget && onClose?.()
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal-card",
    role: "dialog",
    "aria-modal": "true"
  }, title && /*#__PURE__*/React.createElement("div", {
    className: "modal-title"
  }, title), subtitle && /*#__PURE__*/React.createElement("div", {
    className: "modal-sub"
  }, subtitle), children, footer && /*#__PURE__*/React.createElement("div", {
    className: "modal-row"
  }, footer)));
}
Object.assign(__ds_scope, { Modal });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/overlay/Modal.jsx", error: String((e && e.message) || e) }); }

// ui_kits/admin/AdminApp.jsx
try { (() => {
/* Admin portal — self-contained interactive recreation.
   All micro-components inlined — no _ds_bundle.js required. */

/* ── Shared helpers ── */
function statusClass(s) {
  return s ? s.toLowerCase().replace(/\s+/g, '-') : '';
}
function StatusBadge({
  status
}) {
  return /*#__PURE__*/React.createElement("span", {
    className: `status-badge ${statusClass(status)}`
  }, status);
}
function ThreadMessage({
  from = 'student',
  meta,
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: `admin-msg-bubble ${from === 'admin' ? 'admin-msg' : 'student'}`
  }, children, meta && /*#__PURE__*/React.createElement("div", {
    className: "admin-msg-meta"
  }, meta));
}
function KpiCard({
  label,
  value,
  sub,
  accent = 'blue'
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: `dash-kpi-card accent-${accent}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "dash-kpi-label"
  }, label), /*#__PURE__*/React.createElement("div", {
    className: "dash-kpi-value"
  }, value), sub && /*#__PURE__*/React.createElement("div", {
    className: "dash-kpi-sub"
  }, sub));
}
function Modal({
  open,
  title,
  subtitle,
  onClose,
  children,
  footer
}) {
  if (!open) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "modal-overlay",
    onClick: e => e.target === e.currentTarget && onClose?.()
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal-card",
    role: "dialog",
    "aria-modal": "true"
  }, title && /*#__PURE__*/React.createElement("div", {
    className: "modal-title"
  }, title), subtitle && /*#__PURE__*/React.createElement("div", {
    className: "modal-sub"
  }, subtitle), children, footer && /*#__PURE__*/React.createElement("div", {
    className: "modal-row"
  }, footer)));
}

/* ── Icons ── */
const AdminIcon = () => /*#__PURE__*/React.createElement("svg", {
  viewBox: "0 0 24 24",
  fill: "#fff",
  width: "16",
  height: "16"
}, /*#__PURE__*/React.createElement("path", {
  d: "M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 3a3 3 0 1 1-3 3 3 3 0 0 1 3-3zm0 14.2a7.2 7.2 0 0 1-6-3.22c.03-1.99 4-3.08 6-3.08s5.97 1.09 6 3.08a7.2 7.2 0 0 1-6 3.22z"
}));

/* ── Login ── */
function AdminLogin({
  onLogin
}) {
  const [u, setU] = React.useState('admin');
  return /*#__PURE__*/React.createElement("div", {
    className: "login-screen"
  }, /*#__PURE__*/React.createElement("div", {
    className: "login-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "login-logo"
  }, /*#__PURE__*/React.createElement(AdminIcon, null)), /*#__PURE__*/React.createElement("div", {
    className: "login-title"
  }, "Admin Portal"), /*#__PURE__*/React.createElement("div", {
    className: "login-sub"
  }, "Sign in to view and manage student tickets"), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Username"), /*#__PURE__*/React.createElement("input", {
    value: u,
    onChange: e => setU(e.target.value),
    onKeyDown: e => e.key === 'Enter' && onLogin(u),
    placeholder: "admin"
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Password"), /*#__PURE__*/React.createElement("input", {
    type: "password",
    defaultValue: "demo",
    onKeyDown: e => e.key === 'Enter' && onLogin(u)
  })), /*#__PURE__*/React.createElement("button", {
    className: "login-btn",
    onClick: () => onLogin(u)
  }, "Sign In")));
}

/* ── Tickets tab ── */
function AdminThread({
  ticket
}) {
  const [reply, setReply] = React.useState('');
  const [status, setStatus] = React.useState('');
  const isTerminal = ['closed', 'Invalid', 'cancelled'].includes(ticket.status);
  return /*#__PURE__*/React.createElement("div", {
    className: "admin-thread-inner"
  }, ticket.linked && ticket.linked.length > 0 && /*#__PURE__*/React.createElement("div", {
    className: "linked-tickets-section"
  }, /*#__PURE__*/React.createElement("div", {
    className: "linked-tickets-label"
  }, "\uD83D\uDD17 Linked Tickets"), /*#__PURE__*/React.createElement("div", {
    className: "linked-tickets-list"
  }, ticket.linked.map(lt => /*#__PURE__*/React.createElement("div", {
    key: lt.ticket_id,
    className: "linked-ticket-badge"
  }, /*#__PURE__*/React.createElement("span", {
    className: "lt-id"
  }, "#", lt.ticket_id), /*#__PURE__*/React.createElement("span", {
    className: "lt-cat"
  }, lt.category), /*#__PURE__*/React.createElement(StatusBadge, {
    status: lt.status
  }), /*#__PURE__*/React.createElement("span", {
    className: "lt-preview"
  }, lt.first_message))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, ticket.messages.map((m, i) => /*#__PURE__*/React.createElement(ThreadMessage, {
    key: i,
    from: m.sender_role === 'admin' ? 'admin' : 'student',
    meta: `${m.sender_role === 'admin' ? 'Admin' : 'Student'} — ${window.hdFmtDate(m.created_at)}`
  }, m.message_text))), !isTerminal && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "admin-reply-area"
  }, /*#__PURE__*/React.createElement("textarea", {
    className: "admin-reply-input",
    value: reply,
    onChange: e => setReply(e.target.value),
    placeholder: "Type your reply...",
    rows: 1
  }), /*#__PURE__*/React.createElement("button", {
    className: "admin-reply-send"
  }, "Send")), /*#__PURE__*/React.createElement("div", {
    className: "admin-status-panel"
  }, /*#__PURE__*/React.createElement("label", null, "Update Status"), /*#__PURE__*/React.createElement("select", {
    className: "admin-status-select",
    value: status,
    onChange: e => setStatus(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: ""
  }, "\u2014 choose a new status \u2014"), /*#__PURE__*/React.createElement("option", null, "In progress"), /*#__PURE__*/React.createElement("option", null, "resolved"), /*#__PURE__*/React.createElement("option", null, "Invalid"), /*#__PURE__*/React.createElement("option", null, "closed")), status === 'In progress' && /*#__PURE__*/React.createElement("textarea", {
    className: "admin-remark-input",
    rows: 2,
    placeholder: "Remark is required for In progress status..."
  }), /*#__PURE__*/React.createElement("button", {
    className: "admin-status-btn"
  }, "Update Status"))), isTerminal && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: 'var(--muted)',
      fontStyle: 'italic',
      marginTop: 8
    }
  }, "Ticket is ", ticket.status, "."), ticket.admin_remark && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: 'var(--blue)',
      fontStyle: 'italic',
      marginTop: 8
    }
  }, "\uD83D\uDCDD Remark: ", ticket.admin_remark), ticket.feedback_rating && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: 'var(--green)',
      marginTop: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "star-display-inline"
  }, [1, 2, 3, 4, 5].map(n => /*#__PURE__*/React.createElement("span", {
    key: n,
    className: `star ${n <= ticket.feedback_rating ? 'filled' : ''}`
  }, "\u2605"))), ' ', "Student feedback: ", ticket.feedback_rating, "/5", ticket.feedback_remark ? ` — ${ticket.feedback_remark}` : '')));
}
function TicketsTab() {
  const [expanded, setExpanded] = React.useState(new Set([1042]));
  const [search, setSearch] = React.useState('');
  const [filter, setFilter] = React.useState('all');
  const all = window.HD_ADMIN_TICKETS || [];
  const q = search.trim().toLowerCase();
  const visible = all.filter(t => filter === 'all' || t.status === filter).filter(t => !q || String(t.ticket_id).includes(q) || t.username.includes(q) || t.category.toLowerCase().includes(q));
  function toggle(id) {
    setExpanded(prev => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }
  return /*#__PURE__*/React.createElement("div", {
    className: "admin-view"
  }, /*#__PURE__*/React.createElement("div", {
    className: "admin-header-row"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "admin-title"
  }, "Admin Dashboard"), /*#__PURE__*/React.createElement("div", {
    className: "admin-subtitle"
  }, "View and respond to all student tickets")), /*#__PURE__*/React.createElement("button", {
    className: "admin-refresh"
  }, "\u21BB Refresh")), /*#__PURE__*/React.createElement("div", {
    className: "filter-bar"
  }, /*#__PURE__*/React.createElement("input", {
    placeholder: "Search by ID, student or category\u2026",
    value: search,
    onChange: e => setSearch(e.target.value)
  }), /*#__PURE__*/React.createElement("select", {
    value: filter,
    onChange: e => setFilter(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: "all"
  }, "All statuses"), /*#__PURE__*/React.createElement("option", {
    value: "new issue"
  }, "New issue"), /*#__PURE__*/React.createElement("option", {
    value: "In progress"
  }, "In progress"), /*#__PURE__*/React.createElement("option", {
    value: "resolved"
  }, "Resolved"), /*#__PURE__*/React.createElement("option", {
    value: "closed"
  }, "Closed"), /*#__PURE__*/React.createElement("option", {
    value: "Invalid"
  }, "Invalid")), /*#__PURE__*/React.createElement("span", {
    className: "filter-count"
  }, visible.length, " of ", all.length, " ticket(s)")), /*#__PURE__*/React.createElement("div", {
    className: "admin-table-wrap"
  }, /*#__PURE__*/React.createElement("table", {
    className: "admin-table"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "#"), /*#__PURE__*/React.createElement("th", null, "Student"), /*#__PURE__*/React.createElement("th", null, "Category"), /*#__PURE__*/React.createElement("th", null, "Status"), /*#__PURE__*/React.createElement("th", null, "Raised"), /*#__PURE__*/React.createElement("th", null, "Msgs"), /*#__PURE__*/React.createElement("th", null, "Actions"))), /*#__PURE__*/React.createElement("tbody", null, visible.map(t => /*#__PURE__*/React.createElement(React.Fragment, {
    key: t.ticket_id
  }, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("strong", null, "#", t.ticket_id)), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 500
    }
  }, t.username), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: 'var(--muted)'
    }
  }, t.department)), /*#__PURE__*/React.createElement("td", null, t.category), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement(StatusBadge, {
    status: t.status
  })), /*#__PURE__*/React.createElement("td", {
    style: {
      fontSize: 12,
      color: 'var(--muted)'
    }
  }, window.hdFmtDate(t.created_at)), /*#__PURE__*/React.createElement("td", {
    style: {
      fontSize: 12,
      color: 'var(--muted)'
    }
  }, t.message_count), /*#__PURE__*/React.createElement("td", null, /*#__PURE__*/React.createElement("button", {
    className: "expand-btn",
    onClick: () => toggle(t.ticket_id)
  }, expanded.has(t.ticket_id) ? 'Hide Thread' : 'View Thread'))), expanded.has(t.ticket_id) && /*#__PURE__*/React.createElement("tr", {
    className: "admin-thread-row"
  }, /*#__PURE__*/React.createElement("td", {
    colSpan: 7
  }, /*#__PURE__*/React.createElement(AdminThread, {
    ticket: t
  })))))))));
}

/* ── Categories tab ── */
function CatTree({
  nodes,
  parent,
  depth,
  onEdit,
  onAdd
}) {
  const children = (nodes || []).filter(n => n.parent === parent);
  if (!children.length) return null;
  return /*#__PURE__*/React.createElement("ul", {
    className: `cat-tree-ul${depth > 0 ? ' nested' : ''}`
  }, children.map(node => /*#__PURE__*/React.createElement("li", {
    key: node.id
  }, /*#__PURE__*/React.createElement("div", {
    className: "cat-node-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "cat-node-label"
  }, node.label), /*#__PURE__*/React.createElement("span", {
    className: "cat-node-id"
  }, node.id), node.is_no_ticket_other && /*#__PURE__*/React.createElement("span", {
    className: "cat-node-badge closed"
  }, "\uD83D\uDED1 No Ticket"), node.question && /*#__PURE__*/React.createElement("span", {
    className: "cat-node-badge has-question"
  }, "? Question"), !node.question && node.generic_answer && !node.is_no_ticket_other && /*#__PURE__*/React.createElement("span", {
    className: "cat-node-badge has-answer"
  }, "\u2713 Answer"), node.is_ticket_node && /*#__PURE__*/React.createElement("span", {
    className: "cat-node-badge is-ticket"
  }, "\uD83C\uDF9F Ticket"), node.is_reopenable && /*#__PURE__*/React.createElement("span", {
    className: "cat-node-badge is-reopenable"
  }, "\uD83D\uDD04 Reopenable"), /*#__PURE__*/React.createElement("button", {
    className: "cat-action-btn",
    onClick: onEdit
  }, "Edit"), !node.is_ticket_node && !node.is_no_ticket_other && !node.generic_answer && /*#__PURE__*/React.createElement("button", {
    className: "cat-action-btn",
    onClick: onAdd
  }, "+ Child"), node.id !== 'root' && /*#__PURE__*/React.createElement("button", {
    className: "cat-action-btn danger"
  }, "Delete")), /*#__PURE__*/React.createElement(CatTree, {
    nodes: nodes,
    parent: node.id,
    depth: depth + 1,
    onEdit: onEdit,
    onAdd: onAdd
  }))));
}
function CategoriesTab() {
  const [modal, setModal] = React.useState(false);
  const [kind, setKind] = React.useState('answer');
  return /*#__PURE__*/React.createElement("div", {
    className: "admin-view"
  }, /*#__PURE__*/React.createElement("div", {
    className: "admin-header-row"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "admin-title"
  }, "Category Manager"), /*#__PURE__*/React.createElement("div", {
    className: "admin-subtitle"
  }, "Build the support flow. Changes go live instantly for students.")), /*#__PURE__*/React.createElement("button", {
    className: "admin-refresh"
  }, "\u21BB Refresh")), /*#__PURE__*/React.createElement("div", {
    className: "cat-tree-wrap"
  }, /*#__PURE__*/React.createElement(CatTree, {
    nodes: window.HD_NODES || [],
    parent: null,
    depth: 0,
    onEdit: () => setModal(true),
    onAdd: () => setModal(true)
  })), /*#__PURE__*/React.createElement("button", {
    className: "admin-refresh",
    style: {
      marginTop: 16,
      alignSelf: 'flex-start'
    },
    onClick: () => setModal(true)
  }, "+ Add Top-Level Category"), /*#__PURE__*/React.createElement(Modal, {
    title: "Add Node",
    subtitle: "Under: \"Examinations & Results\"",
    open: modal,
    onClose: () => setModal(false),
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
      className: "modal-btn secondary",
      onClick: () => setModal(false)
    }, "Cancel"), /*#__PURE__*/React.createElement("button", {
      className: "modal-btn primary",
      onClick: () => setModal(false)
    }, "Save Node"))
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal-field"
  }, /*#__PURE__*/React.createElement("label", null, "Label (displayed to students)"), /*#__PURE__*/React.createElement("input", {
    type: "text",
    placeholder: "e.g. Attendance Shortage"
  })), /*#__PURE__*/React.createElement("div", {
    className: "modal-field"
  }, /*#__PURE__*/React.createElement("label", null, "Node Behaviour"), /*#__PURE__*/React.createElement("div", {
    className: "radio-group"
  }, [['nav', 'Sub-category (navigation)', 'Acts as a menu item. Add children via + Child.'], ['question', 'Ask a follow-up question', 'Student is shown a question and picks an option.'], ['answer', 'Show a generic answer', 'Student sees a pre-written response.'], ['ticket', 'Raise a support ticket', 'Student is asked to submit a support ticket.']].map(([v, t, d]) => /*#__PURE__*/React.createElement("label", {
    key: v,
    className: "radio-option"
  }, /*#__PURE__*/React.createElement("input", {
    type: "radio",
    name: "kind",
    checked: kind === v,
    onChange: () => setKind(v)
  }), /*#__PURE__*/React.createElement("div", {
    className: "radio-option-text"
  }, /*#__PURE__*/React.createElement("strong", null, t), /*#__PURE__*/React.createElement("span", null, d)))))), kind === 'answer' && /*#__PURE__*/React.createElement("div", {
    className: "modal-field"
  }, /*#__PURE__*/React.createElement("label", null, "Generic Answer Text"), /*#__PURE__*/React.createElement("textarea", {
    placeholder: "Type the answer students will see..."
  })), kind === 'question' && /*#__PURE__*/React.createElement("div", {
    className: "modal-field"
  }, /*#__PURE__*/React.createElement("label", null, "Question Text (shown to student)"), /*#__PURE__*/React.createElement("input", {
    type: "text",
    placeholder: "e.g. What is the specific issue?"
  })), /*#__PURE__*/React.createElement("div", {
    className: "modal-field",
    style: {
      marginTop: 16
    }
  }, /*#__PURE__*/React.createElement("label", {
    className: "checkbox-option"
  }, /*#__PURE__*/React.createElement("input", {
    type: "checkbox",
    defaultChecked: true
  }), /*#__PURE__*/React.createElement("div", {
    className: "radio-option-text"
  }, /*#__PURE__*/React.createElement("strong", null, "Allow students to reopen tickets"), /*#__PURE__*/React.createElement("span", null, "Applies to this category and all its sub-nodes."))))));
}

/* ── Dashboard tab ── */
function DashboardTab() {
  const s = window.HD_STATS || {
    total_conversations: 0,
    total_logs: 0,
    total_tickets: 0,
    total_feedback: 0,
    avg_rating: 0,
    categories: []
  };
  const canvasRef = React.useRef(null);
  React.useEffect(() => {
    if (!window.Chart || !canvasRef.current) return;
    const palette = ['#7c3aed', '#2563eb', '#16a34a', '#d97706', '#be123c', '#0891b2'];
    const chart = new window.Chart(canvasRef.current, {
      type: 'bar',
      data: {
        labels: s.categories.map(c => c.category),
        datasets: [{
          data: s.categories.map(c => c.count),
          backgroundColor: s.categories.map((_, i) => palette[i % palette.length] + 'cc'),
          borderColor: s.categories.map((_, i) => palette[i % palette.length]),
          borderWidth: 1,
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          x: {
            grid: {
              display: false
            }
          },
          y: {
            beginAtZero: true,
            grid: {
              color: '#e2e5ea'
            },
            ticks: {
              precision: 0
            }
          }
        }
      }
    });
    return () => chart.destroy();
  }, []);
  return /*#__PURE__*/React.createElement("div", {
    className: "admin-view"
  }, /*#__PURE__*/React.createElement("div", {
    className: "admin-header-row"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "admin-title"
  }, "Dashboard"), /*#__PURE__*/React.createElement("div", {
    className: "admin-subtitle"
  }, "Conversation and ticket analytics at a glance")), /*#__PURE__*/React.createElement("button", {
    className: "admin-refresh"
  }, "\u21BB Refresh")), /*#__PURE__*/React.createElement("div", {
    className: "dash-kpi-grid"
  }, /*#__PURE__*/React.createElement(KpiCard, {
    accent: "blue",
    label: "Total Conversations",
    value: s.total_conversations.toLocaleString(),
    sub: "tickets + direct responses"
  }), /*#__PURE__*/React.createElement(KpiCard, {
    accent: "green",
    label: "Direct Responses",
    value: s.total_logs.toLocaleString(),
    sub: "resolved without a ticket"
  }), /*#__PURE__*/React.createElement(KpiCard, {
    accent: "orange",
    label: "Tickets Raised",
    value: s.total_tickets,
    sub: "submitted to support queue"
  }), /*#__PURE__*/React.createElement(KpiCard, {
    accent: "purple",
    label: "Average Rating",
    value: `${s.avg_rating} / 5`,
    sub: `from ${s.total_feedback} rated tickets`
  })), /*#__PURE__*/React.createElement("div", {
    className: "dash-chart-wrap"
  }, /*#__PURE__*/React.createElement("div", {
    className: "dash-chart-title"
  }, "Tickets by Category"), /*#__PURE__*/React.createElement("div", {
    className: "dash-chart-canvas-wrap"
  }, /*#__PURE__*/React.createElement("canvas", {
    ref: canvasRef
  }))));
}

/* ── Tab bar ── */
function Tabs({
  tabs,
  active,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "tab-bar"
  }, tabs.map(t => /*#__PURE__*/React.createElement("button", {
    key: t.id,
    className: `tab-btn ${active === t.id ? 'active' : ''}`,
    onClick: () => onChange(t.id)
  }, t.label)));
}

/* ── Shell ── */
function AdminApp() {
  const [user, setUser] = React.useState(null);
  const [tab, setTab] = React.useState('tickets');
  if (!user) {
    return /*#__PURE__*/React.createElement("div", {
      className: "admin-portal"
    }, /*#__PURE__*/React.createElement(AdminLogin, {
      onLogin: setUser
    }));
  }
  return /*#__PURE__*/React.createElement("div", {
    className: "admin-portal",
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: '100vh'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "header-left"
  }, /*#__PURE__*/React.createElement("div", {
    className: "header-icon admin-icon"
  }, /*#__PURE__*/React.createElement(AdminIcon, null)), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "header-title"
  }, "Admin Portal"), /*#__PURE__*/React.createElement("div", {
    className: "header-sub"
  }, "Signed in as ", user))), /*#__PURE__*/React.createElement("div", {
    className: "header-right"
  }, /*#__PURE__*/React.createElement("span", {
    className: "hdr-badge admin"
  }, "Admin"), /*#__PURE__*/React.createElement("button", {
    className: "hdr-btn",
    onClick: () => setUser(null)
  }, "Sign Out"))), /*#__PURE__*/React.createElement(Tabs, {
    active: tab,
    onChange: setTab,
    tabs: [{
      id: 'tickets',
      label: '🎟 Tickets'
    }, {
      id: 'categories',
      label: '🗂 Categories'
    }, {
      id: 'dashboard',
      label: '📊 Dashboard'
    }]
  }), /*#__PURE__*/React.createElement("div", {
    className: "admin-content-area"
  }, tab === 'tickets' && /*#__PURE__*/React.createElement(TicketsTab, null), tab === 'categories' && /*#__PURE__*/React.createElement(CategoriesTab, null), tab === 'dashboard' && /*#__PURE__*/React.createElement(DashboardTab, null)));
}
window.AdminApp = AdminApp;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/admin/AdminApp.jsx", error: String((e && e.message) || e) }); }

// ui_kits/admin/data.js
try { (() => {
/* Fake data for the Admin portal UI kit. */
window.HD_ADMIN_TICKETS = [{
  ticket_id: 1042,
  username: 'alice',
  department: 'Computer Science · Sem 6',
  category: 'Examinations & Results',
  status: 'In progress',
  created_at: '2026-06-10T09:14:00',
  message_count: 2,
  admin_remark: 'Forwarded to the examination cell for verification.',
  messages: [{
    sender_role: 'student',
    message_text: 'I requested revaluation of my DBMS paper but the status has not changed in two weeks.',
    created_at: '2026-06-10T09:14:00'
  }, {
    sender_role: 'admin',
    message_text: "We've forwarded your request to the examination cell. You'll hear back within 5 working days.",
    created_at: '2026-06-11T15:02:00'
  }],
  linked: [{
    ticket_id: 1018,
    category: 'Examinations & Results',
    status: 'closed',
    first_message: 'Result not published for one subject.'
  }]
}, {
  ticket_id: 1041,
  username: 'rahul',
  department: 'Mechanical · Sem 4',
  category: 'Fees & Payments',
  status: 'new issue',
  created_at: '2026-06-12T08:02:00',
  message_count: 1,
  admin_remark: '',
  messages: [{
    sender_role: 'student',
    message_text: 'My scholarship amount has not been adjusted against this semester fee.',
    created_at: '2026-06-12T08:02:00'
  }],
  linked: []
}, {
  ticket_id: 1039,
  username: 'meera',
  department: 'Electronics · Sem 8',
  category: 'Fees & Payments',
  status: 'resolved',
  created_at: '2026-06-08T11:40:00',
  message_count: 2,
  admin_remark: '',
  messages: [{
    sender_role: 'student',
    message_text: 'My fee payment failed but the amount was debited.',
    created_at: '2026-06-08T11:40:00'
  }, {
    sender_role: 'admin',
    message_text: 'The failed transaction has been reversed. Marking this resolved.',
    created_at: '2026-06-09T10:20:00'
  }],
  linked: []
}, {
  ticket_id: 1021,
  username: 'john',
  department: 'Civil · Sem 2',
  category: 'Hostel & Facilities',
  status: 'closed',
  created_at: '2026-05-29T18:05:00',
  message_count: 3,
  admin_remark: '',
  feedback_rating: 5,
  feedback_remark: 'Quick and helpful, thanks!',
  messages: [{
    sender_role: 'student',
    message_text: 'The Wi-Fi in Block C has been down for three days.',
    created_at: '2026-05-29T18:05:00'
  }, {
    sender_role: 'admin',
    message_text: 'Network team has restored the Block C access point.',
    created_at: '2026-05-30T09:30:00'
  }, {
    sender_role: 'student',
    message_text: "It's working now, thank you!",
    created_at: '2026-05-30T12:11:00'
  }],
  linked: []
}, {
  ticket_id: 1009,
  username: 'sara',
  department: 'Computer Science · Sem 6',
  category: 'Attendance & Leave',
  status: 'Invalid',
  created_at: '2026-05-22T14:20:00',
  message_count: 1,
  admin_remark: 'Duplicate of #1004.',
  messages: [{
    sender_role: 'student',
    message_text: 'My attendance is showing wrong for May.',
    created_at: '2026-05-22T14:20:00'
  }],
  linked: []
}];
window.HD_NODES = [{
  id: 'root',
  label: 'Home',
  parent: null
}, {
  id: 'attendance',
  label: 'Attendance & Leave',
  parent: 'root',
  is_reopenable: true
}, {
  id: 'att_short',
  label: 'My attendance is short',
  parent: 'attendance',
  generic_answer: 'Attendance below 75% is flagged…',
  is_reopenable: true
}, {
  id: 'att_leave',
  label: 'Apply for medical leave',
  parent: 'attendance',
  generic_answer: 'Submit your medical certificate…'
}, {
  id: 'exams',
  label: 'Examinations & Results',
  parent: 'root',
  is_reopenable: true
}, {
  id: 'exam_reval',
  label: 'Request revaluation',
  parent: 'exams',
  is_ticket_node: true,
  is_reopenable: true
}, {
  id: 'exam_hall',
  label: 'Hall ticket not generated',
  parent: 'exams',
  is_ticket_node: true
}, {
  id: 'fees',
  label: 'Fees & Payments',
  parent: 'root',
  question: 'What is your payment issue?'
}, {
  id: 'hostel',
  label: 'Hostel & Facilities',
  parent: 'root'
}, {
  id: 'hostel_room',
  label: 'Room change request',
  parent: 'hostel',
  is_ticket_node: true
}, {
  id: 'hostel_other',
  label: 'Something else',
  parent: 'hostel',
  is_no_ticket_other: true,
  generic_answer: 'Please contact the hostel office directly.'
}];
window.HD_STATS = {
  total_conversations: 1284,
  total_logs: 942,
  total_tickets: 342,
  total_feedback: 210,
  avg_rating: 4.6,
  categories: [{
    category: 'Examinations',
    count: 96
  }, {
    category: 'Fees',
    count: 81
  }, {
    category: 'Attendance',
    count: 64
  }, {
    category: 'Hostel',
    count: 52
  }, {
    category: 'Library',
    count: 28
  }, {
    category: 'Other',
    count: 21
  }]
};
window.hdFmtDate = function (raw) {
  try {
    const d = new Date(raw);
    return d.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    }) + ' ' + d.toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (_) {
    return raw;
  }
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/admin/data.js", error: String((e && e.message) || e) }); }

// ui_kits/student/StudentApp.jsx
try { (() => {
/* Student portal — self-contained interactive recreation.
   All micro-components inlined — no _ds_bundle.js required. */

/* ── Shared helpers ── */
function statusClass(s) {
  return s ? s.toLowerCase().replace(/\s+/g, '-') : '';
}
function StatusBadge({
  status
}) {
  return /*#__PURE__*/React.createElement("span", {
    className: `status-badge ${statusClass(status)}`
  }, status);
}
function OptionButton({
  label,
  children,
  onClick,
  disabled
}) {
  return /*#__PURE__*/React.createElement("button", {
    className: "opt-btn",
    onClick: onClick,
    disabled: disabled
  }, /*#__PURE__*/React.createElement("span", null, label ?? children), /*#__PURE__*/React.createElement("span", {
    className: "arrow"
  }, "\u203A"));
}
function ChoiceButtons({
  yesLabel = "Yes",
  noLabel = "No",
  onYes,
  onNo,
  disabled
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "yesno-row"
  }, /*#__PURE__*/React.createElement("button", {
    className: "yn-btn yes",
    onClick: onYes,
    disabled: disabled
  }, yesLabel), /*#__PURE__*/React.createElement("button", {
    className: "yn-btn no",
    onClick: onNo,
    disabled: disabled
  }, noLabel));
}
function ChatBubble({
  from = 'support',
  label,
  children
}) {
  const isUser = from === 'user';
  return /*#__PURE__*/React.createElement("div", {
    className: "msg"
  }, /*#__PURE__*/React.createElement("div", {
    className: `msg-label ${isUser ? 'right' : ''}`
  }, label ?? (isUser ? 'You' : 'Support')), /*#__PURE__*/React.createElement("div", {
    className: `bubble ${isUser ? 'user' : ''}`
  }, children));
}
function TypingIndicator() {
  return /*#__PURE__*/React.createElement("div", {
    className: "typing-indicator"
  }, /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("span", null));
}
function ThreadMessage({
  from = 'student',
  meta,
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: `msg-bubble ${from === 'student' ? 'student' : 'admin'}`
  }, children, meta && /*#__PURE__*/React.createElement("div", {
    className: "msg-meta"
  }, meta));
}
function StarRating({
  value = 0,
  readOnly = false,
  onChange,
  disabled
}) {
  const [hover, setHover] = React.useState(0);
  if (readOnly) {
    return /*#__PURE__*/React.createElement("span", {
      className: "star-display"
    }, [1, 2, 3, 4, 5].map(n => /*#__PURE__*/React.createElement("span", {
      key: n,
      className: `star ${n <= value ? 'filled' : ''}`
    }, "\u2605")));
  }
  const display = hover || value;
  return /*#__PURE__*/React.createElement("div", {
    className: "star-rating"
  }, [1, 2, 3, 4, 5].map(n => /*#__PURE__*/React.createElement("button", {
    key: n,
    type: "button",
    className: `star-btn ${n <= display ? 'filled' : ''}`,
    onClick: () => onChange?.(n),
    onMouseEnter: () => setHover(n),
    onMouseLeave: () => setHover(0),
    disabled: disabled
  }, "\u2605")));
}
function SkeletonGroup({
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "skeleton-wrap"
  }, children);
}
function Skeleton({
  variant = 'line',
  width
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: `skeleton skeleton-${variant}`,
    style: width ? {
      width
    } : {}
  });
}

/* ── Icons ── */
const ChatIcon = () => /*#__PURE__*/React.createElement("svg", {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "#fff",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
}));
const CheckIcon = () => /*#__PURE__*/React.createElement("svg", {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "#fff",
  strokeWidth: "2.5",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("polyline", {
  points: "20 6 9 17 4 12"
}));
const TicketIcon = () => /*#__PURE__*/React.createElement("svg", {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "#fff",
  strokeWidth: "2.5",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, /*#__PURE__*/React.createElement("path", {
  d: "M15 5v2M15 11v2M15 17v2M5 5h14a2 2 0 0 1 2 2v3a2 2 0 0 0 0 4v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3a2 2 0 0 0 0-4V7a2 2 0 0 1 2-2z"
}));

/* ── Login ── */
function StudentLogin({
  onLogin
}) {
  const [u, setU] = React.useState('alice');
  const [p, setP] = React.useState('demo');
  return /*#__PURE__*/React.createElement("div", {
    className: "login-screen"
  }, /*#__PURE__*/React.createElement("div", {
    className: "login-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "login-logo"
  }, /*#__PURE__*/React.createElement(ChatIcon, null)), /*#__PURE__*/React.createElement("div", {
    className: "login-title"
  }, "Student Help Desk"), /*#__PURE__*/React.createElement("div", {
    className: "login-sub"
  }, "Sign in to raise or track a support request"), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Username"), /*#__PURE__*/React.createElement("input", {
    value: u,
    onChange: e => setU(e.target.value),
    onKeyDown: e => e.key === 'Enter' && onLogin(u),
    placeholder: "e.g. alice"
  })), /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, /*#__PURE__*/React.createElement("label", null, "Password"), /*#__PURE__*/React.createElement("input", {
    type: "password",
    value: p,
    onChange: e => setP(e.target.value),
    onKeyDown: e => e.key === 'Enter' && onLogin(u)
  })), /*#__PURE__*/React.createElement("button", {
    className: "login-btn",
    onClick: () => onLogin(u)
  }, "Sign In")));
}

/* ── Resolution & ticket cards ── */
function ResolutionCard({
  text
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "resolution-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "res-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "res-icon"
  }, /*#__PURE__*/React.createElement(CheckIcon, null)), /*#__PURE__*/React.createElement("span", {
    className: "res-title"
  }, "Solution")), text);
}
function TicketConfirm({
  summary,
  onSubmit,
  onCancel
}) {
  const [text, setText] = React.useState(summary);
  return /*#__PURE__*/React.createElement("div", {
    className: "ticket-confirm-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "tc-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "tc-icon"
  }, /*#__PURE__*/React.createElement(TicketIcon, null)), /*#__PURE__*/React.createElement("span", {
    className: "tc-title"
  }, "Raise a Ticket")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: 'var(--muted)',
      marginBottom: 8
    }
  }, "Review and edit the description below before submitting."), /*#__PURE__*/React.createElement("textarea", {
    className: "ticket-edit-textarea",
    value: text,
    onChange: e => setText(e.target.value)
  }), /*#__PURE__*/React.createElement("div", {
    className: "file-upload-row"
  }, /*#__PURE__*/React.createElement("div", {
    className: "file-upload-label"
  }, "\uD83D\uDCCE Attach a file or screenshot (optional \xB7 max 10 MB)"), /*#__PURE__*/React.createElement("input", {
    type: "file",
    className: "file-input"
  })), /*#__PURE__*/React.createElement("div", {
    className: "tc-question"
  }, "Submit this ticket?"), /*#__PURE__*/React.createElement(ChoiceButtons, {
    yesLabel: "Yes, submit ticket",
    noLabel: "No, cancel",
    onYes: () => onSubmit(text),
    onNo: onCancel
  }));
}
function TicketRaised({
  ticketId,
  onNew,
  onView
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "ticket-raised-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "tr-header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "tr-icon"
  }, /*#__PURE__*/React.createElement(CheckIcon, null)), /*#__PURE__*/React.createElement("span", {
    className: "tr-title"
  }, "Ticket Raised")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      marginBottom: 8
    }
  }, "Your ticket has been raised. Our team will respond within 24\u201348 hours."), /*#__PURE__*/React.createElement("div", {
    className: "tr-id",
    onClick: onView,
    style: {
      cursor: 'pointer',
      textDecoration: 'underline'
    }
  }, "Ticket ID: #", ticketId), /*#__PURE__*/React.createElement("div", {
    className: "options-list",
    style: {
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement(OptionButton, {
    label: "Start a new request",
    onClick: onNew
  }), /*#__PURE__*/React.createElement(OptionButton, {
    label: "View My Tickets",
    onClick: onView
  })));
}

/* ── Chat view ── */
function ChatView({
  onOpenTickets
}) {
  const [history, setHistory] = React.useState([{
    type: 'support',
    text: 'Hi! How can we help you today? Choose a category to get started.'
  }]);
  const [crumbs, setCrumbs] = React.useState(['Home']);
  const [typing, setTyping] = React.useState(false);
  const [interactive, setInteractive] = React.useState({
    type: 'options',
    node: 'root'
  });
  const chatAreaRef = React.useRef(null);
  const bottomRef = React.useRef(null);
  React.useEffect(() => {
    if (chatAreaRef.current) chatAreaRef.current.scrollTop = chatAreaRef.current.scrollHeight;
  }, [history, interactive, typing]);
  function go(id, label) {
    setHistory(h => [...h, {
      type: 'user',
      text: label
    }]);
    setCrumbs(c => [...c, label]);
    setInteractive(null);
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      const n = window.HD_TREE[id];
      if (!n) return;
      if (n.ticket) {
        setHistory(h => [...h, {
          type: 'support',
          text: "Let's raise a ticket so our team can help with this."
        }]);
        setInteractive({
          type: 'confirm',
          summary: n.summary
        });
      } else if (n.answer) {
        setHistory(h => [...h, {
          type: 'resolution',
          text: n.answer
        }]);
        setInteractive(n.canTicket ? {
          type: 'offer'
        } : {
          type: 'restart'
        });
      } else {
        setHistory(h => [...h, {
          type: 'support',
          text: 'Which of these is closest to your issue?'
        }]);
        setInteractive({
          type: 'options',
          node: id
        });
      }
    }, 650);
  }
  function submitTicket() {
    setInteractive(null);
    setHistory(h => [...h, {
      type: 'user',
      text: 'Yes, submit ticket'
    }, {
      type: 'support',
      text: 'Ticket submitted — you will receive a response within 24–48 hours.'
    }]);
    setInteractive({
      type: 'raised',
      ticketId: 1043
    });
  }
  function restart() {
    setHistory([{
      type: 'support',
      text: 'Hi! How can we help you today? Choose a category to get started.'
    }]);
    setCrumbs(['Home']);
    setInteractive({
      type: 'options',
      node: 'root'
    });
  }
  const tree = window.HD_TREE || {};
  return /*#__PURE__*/React.createElement("div", {
    className: "chat-view"
  }, /*#__PURE__*/React.createElement("div", {
    className: "breadcrumb"
  }, crumbs.map((c, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 4
    }
  }, i > 0 && /*#__PURE__*/React.createElement("span", {
    className: "bc-sep"
  }, "\u203A"), /*#__PURE__*/React.createElement("span", {
    className: `bc-item ${i === crumbs.length - 1 ? 'active' : ''}`
  }, c)))), /*#__PURE__*/React.createElement("div", {
    className: "chat-area",
    ref: chatAreaRef
  }, history.map((m, i) => {
    if (m.type === 'support') return /*#__PURE__*/React.createElement(ChatBubble, {
      key: i,
      from: "support"
    }, m.text);
    if (m.type === 'user') return /*#__PURE__*/React.createElement(ChatBubble, {
      key: i,
      from: "user"
    }, m.text);
    if (m.type === 'resolution') return /*#__PURE__*/React.createElement(ResolutionCard, {
      key: i,
      text: m.text
    });
    return null;
  }), typing && /*#__PURE__*/React.createElement(TypingIndicator, null), !typing && interactive?.type === 'options' && tree[interactive.node] && /*#__PURE__*/React.createElement("div", {
    className: "options-list"
  }, (tree[interactive.node].options || []).map(o => /*#__PURE__*/React.createElement(OptionButton, {
    key: o.id,
    label: o.label,
    onClick: () => go(o.id, o.label)
  }))), !typing && interactive?.type === 'confirm' && /*#__PURE__*/React.createElement(TicketConfirm, {
    summary: interactive.summary,
    onSubmit: submitTicket,
    onCancel: restart
  }), !typing && interactive?.type === 'raised' && /*#__PURE__*/React.createElement(TicketRaised, {
    ticketId: interactive.ticketId,
    onNew: restart,
    onView: onOpenTickets
  }), !typing && interactive?.type === 'offer' && /*#__PURE__*/React.createElement("div", {
    className: "optional-ticket-offer"
  }, /*#__PURE__*/React.createElement("div", {
    className: "oto-text"
  }, "Not satisfied with this answer?"), /*#__PURE__*/React.createElement("div", {
    className: "yesno-row",
    style: {
      marginTop: 8
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "yn-btn yes",
    onClick: () => setInteractive({
      type: 'confirm',
      summary: 'Student needs further help after viewing the self-service answer.'
    })
  }, "Raise a Ticket"), /*#__PURE__*/React.createElement("button", {
    className: "yn-btn no",
    onClick: restart
  }, "No, I'm good"))), !typing && interactive?.type === 'restart' && /*#__PURE__*/React.createElement("div", {
    className: "options-list"
  }, /*#__PURE__*/React.createElement(OptionButton, {
    label: "Start a new request",
    onClick: restart
  })), /*#__PURE__*/React.createElement("div", {
    ref: bottomRef,
    style: {
      height: 1,
      flexShrink: 0
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "chat-footer"
  }, /*#__PURE__*/React.createElement("div", {
    className: "chat-footer-left"
  }, /*#__PURE__*/React.createElement("button", {
    className: "ctrl-btn back-btn",
    onClick: restart
  }, "\u2190 Back")), /*#__PURE__*/React.createElement("div", {
    className: "chat-footer-center"
  }, /*#__PURE__*/React.createElement("textarea", {
    className: "reply-input",
    placeholder: "Or type your issue here\u2026",
    rows: 1
  }), /*#__PURE__*/React.createElement("button", {
    className: "reply-send"
  }, "Send")), /*#__PURE__*/React.createElement("div", {
    className: "chat-footer-right"
  }, /*#__PURE__*/React.createElement("button", {
    className: "ctrl-btn restart-btn",
    onClick: restart
  }, "Restart"))));
}

/* ── Thread view ── */
function ThreadView({
  ticket,
  onBack
}) {
  const [reply, setReply] = React.useState('');
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "thread-header"
  }, /*#__PURE__*/React.createElement("button", {
    className: "thread-back",
    onClick: onBack
  }, "\u2039"), /*#__PURE__*/React.createElement("div", {
    className: "thread-ticket-info"
  }, /*#__PURE__*/React.createElement("div", {
    className: "thread-ticket-id"
  }, "#", ticket.ticket_id, "\xA0", /*#__PURE__*/React.createElement(StatusBadge, {
    status: ticket.status
  })), /*#__PURE__*/React.createElement("div", {
    className: "thread-ticket-cat"
  }, ticket.category))), /*#__PURE__*/React.createElement("div", {
    className: "thread-messages"
  }, ticket.messages.map((m, i) => /*#__PURE__*/React.createElement(ThreadMessage, {
    key: i,
    from: m.sender_role,
    meta: `${m.sender_role === 'admin' ? 'Admin' : 'You'} — ${window.hdFmtDate(m.created_at)}`
  }, m.message_text))), /*#__PURE__*/React.createElement("div", {
    className: "thread-footer"
  }, ticket.status === 'closed' ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "thread-status-msg"
  }, "This ticket is closed."), /*#__PURE__*/React.createElement("div", {
    className: "feedback-section"
  }, /*#__PURE__*/React.createElement("div", {
    className: "feedback-done"
  }, /*#__PURE__*/React.createElement("div", {
    className: "star-display"
  }, /*#__PURE__*/React.createElement(StarRating, {
    value: ticket.feedback_rating || 0,
    readOnly: true
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 6
    }
  }, "Feedback submitted \u2014 thank you!"))))) : ticket.status === 'resolved' ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "thread-status-msg resolved-active-note"
  }, "\u2705 Admin has marked this resolved \u2014 reply if you still need help, or close the ticket."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("textarea", {
    className: "reply-input",
    value: reply,
    onChange: e => setReply(e.target.value),
    placeholder: "Type your reply\u2026",
    rows: 1,
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("button", {
    className: "reply-send"
  }, "Send")), /*#__PURE__*/React.createElement("button", {
    className: "close-ticket-btn"
  }, "Close Ticket")) : /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("textarea", {
    className: "reply-input",
    value: reply,
    onChange: e => setReply(e.target.value),
    placeholder: "Type your reply\u2026",
    rows: 1,
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("button", {
    className: "reply-send"
  }, "Send"))));
}

/* ── Tickets panel ── */
function TicketsPanel({
  open,
  onClose
}) {
  const [active, setActive] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  React.useEffect(() => {
    if (!open) setActive(null);
  }, [open]);
  function openThread(id) {
    setLoading(true);
    setActive(id);
    setTimeout(() => setLoading(false), 500);
  }
  const ticket = (window.HD_TICKETS || []).find(t => t.ticket_id === active);
  return /*#__PURE__*/React.createElement("div", {
    className: `tickets-panel ${open ? 'open' : ''}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "panel-header"
  }, /*#__PURE__*/React.createElement("span", {
    className: "panel-title"
  }, active ? `Ticket #${active}` : 'My Tickets'), /*#__PURE__*/React.createElement("button", {
    className: "panel-close",
    onClick: onClose
  }, "\u2715")), !active && /*#__PURE__*/React.createElement("div", {
    className: "panel-search-wrap"
  }, /*#__PURE__*/React.createElement("input", {
    className: "panel-search",
    placeholder: "Search by ID, category or description\u2026"
  })), /*#__PURE__*/React.createElement("div", {
    className: "panel-body"
  }, !active && (window.HD_TICKETS || []).map(t => /*#__PURE__*/React.createElement("div", {
    key: t.ticket_id,
    className: "ticket-list-item",
    onClick: () => openThread(t.ticket_id)
  }, /*#__PURE__*/React.createElement("div", {
    className: "tli-content"
  }, /*#__PURE__*/React.createElement("div", {
    className: "tli-top"
  }, /*#__PURE__*/React.createElement("span", {
    className: "tli-id"
  }, "#", t.ticket_id), /*#__PURE__*/React.createElement(StatusBadge, {
    status: t.status
  })), /*#__PURE__*/React.createElement("div", {
    className: "tli-category"
  }, t.category), /*#__PURE__*/React.createElement("div", {
    className: "tli-preview"
  }, (t.first_message || '').slice(0, 80)), t.status === 'In progress' && t.admin_remark && /*#__PURE__*/React.createElement("div", {
    className: "tli-remark"
  }, "\u270F\uFE0F Admin: ", t.admin_remark), /*#__PURE__*/React.createElement("div", {
    className: "tli-date"
  }, window.hdFmtDate(t.created_at))))), active && loading && /*#__PURE__*/React.createElement(SkeletonGroup, null, /*#__PURE__*/React.createElement(Skeleton, {
    variant: "line",
    width: "40%"
  }), /*#__PURE__*/React.createElement(Skeleton, {
    variant: "card"
  }), /*#__PURE__*/React.createElement(Skeleton, {
    variant: "card",
    width: "80%"
  })), active && !loading && ticket && /*#__PURE__*/React.createElement(ThreadView, {
    ticket: ticket,
    onBack: () => setActive(null)
  })));
}

/* ── App shell ── */
function StudentApp() {
  const [user, setUser] = React.useState(null);
  const [panel, setPanel] = React.useState(false);
  const [notif, setNotif] = React.useState(true);
  if (!user) return /*#__PURE__*/React.createElement(StudentLogin, {
    onLogin: setUser
  });
  return /*#__PURE__*/React.createElement("div", {
    className: "app-shell"
  }, /*#__PURE__*/React.createElement("div", {
    className: "header"
  }, /*#__PURE__*/React.createElement("div", {
    className: "header-left"
  }, /*#__PURE__*/React.createElement("div", {
    className: "header-icon"
  }, /*#__PURE__*/React.createElement(ChatIcon, null)), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "header-title"
  }, "Student Help Desk"), /*#__PURE__*/React.createElement("div", {
    className: "header-sub"
  }, "Signed in as ", user))), /*#__PURE__*/React.createElement("div", {
    className: "header-right"
  }, /*#__PURE__*/React.createElement("span", {
    className: "hdr-badge online"
  }, "Student"), /*#__PURE__*/React.createElement("button", {
    className: "hdr-btn tickets-btn",
    onClick: () => setPanel(p => !p)
  }, "My Tickets ", notif && /*#__PURE__*/React.createElement("span", {
    className: "notif-badge"
  }, "2")), /*#__PURE__*/React.createElement("button", {
    className: "hdr-btn",
    onClick: () => setUser(null)
  }, "Sign Out"))), notif && /*#__PURE__*/React.createElement("div", {
    className: "notif-banner"
  }, /*#__PURE__*/React.createElement("span", null, "\uD83D\uDD14 You have ", /*#__PURE__*/React.createElement("strong", null, "2"), " ticket updates since your last visit.", ' ', /*#__PURE__*/React.createElement("a", {
    onClick: () => {
      setPanel(true);
      setNotif(false);
    }
  }, "View My Tickets")), /*#__PURE__*/React.createElement("button", {
    className: "notif-close",
    onClick: () => setNotif(false)
  }, "\u2715")), /*#__PURE__*/React.createElement("div", {
    className: "content-area"
  }, /*#__PURE__*/React.createElement(ChatView, {
    onOpenTickets: () => setPanel(true)
  }), /*#__PURE__*/React.createElement(TicketsPanel, {
    open: panel,
    onClose: () => setPanel(false)
  })));
}
window.StudentApp = StudentApp;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/student/StudentApp.jsx", error: String((e && e.message) || e) }); }

// ui_kits/student/data.js
try { (() => {
/* Fake data for the Student portal UI kit (no backend). */
window.HD_TREE = {
  root: {
    label: 'Home',
    options: [{
      id: 'attendance',
      label: 'Attendance & Leave'
    }, {
      id: 'exams',
      label: 'Examinations & Results'
    }, {
      id: 'fees',
      label: 'Fees & Payments'
    }, {
      id: 'hostel',
      label: 'Hostel & Facilities'
    }]
  },
  attendance: {
    label: 'Attendance & Leave',
    options: [{
      id: 'att_short',
      label: 'My attendance is short'
    }, {
      id: 'att_leave',
      label: 'Apply for medical leave'
    }]
  },
  att_short: {
    label: 'My attendance is short',
    answer: 'Attendance below 75% is flagged to your department. If you believe there is an error in your record, raise a ticket and the office will verify it against the register within 2 working days.',
    canTicket: true
  },
  att_leave: {
    label: 'Apply for medical leave',
    answer: 'Submit your medical certificate through the Leave portal under Student Services. Leave is approved by your class coordinator. No ticket is required for standard medical leave.',
    canTicket: false
  },
  exams: {
    label: 'Examinations & Results',
    options: [{
      id: 'exam_reval',
      label: 'Request revaluation'
    }, {
      id: 'exam_hall',
      label: "Hall ticket not generated"
    }]
  },
  exam_reval: {
    label: 'Request revaluation',
    ticket: true,
    summary: 'Student requests revaluation of their semester examination result. They believe the awarded marks do not reflect their answers and would like a recheck.'
  },
  exam_hall: {
    label: 'Hall ticket not generated',
    ticket: true,
    summary: 'Student cannot generate their examination hall ticket. The portal shows no hall ticket available despite fees being paid.'
  },
  fees: {
    label: 'Fees & Payments',
    answer: 'Semester fees can be paid online via the Fees portal. Receipts are generated instantly. For failed transactions where money was debited, raise a ticket with your transaction reference.',
    canTicket: true
  },
  hostel: {
    label: 'Hostel & Facilities',
    options: [{
      id: 'hostel_room',
      label: 'Room change request'
    }, {
      id: 'hostel_maint',
      label: 'Maintenance complaint'
    }]
  },
  hostel_room: {
    label: 'Room change request',
    ticket: true,
    summary: 'Student requests a hostel room change citing issues with their current allocation.'
  },
  hostel_maint: {
    label: 'Maintenance complaint',
    ticket: true,
    summary: 'Student reports a maintenance issue in their hostel room that needs attention from the facilities team.'
  }
};
window.HD_TICKETS = [{
  ticket_id: 1042,
  category: 'Examinations & Results',
  status: 'In progress',
  first_message: 'I requested revaluation of my DBMS paper but the status has not changed in two weeks.',
  created_at: '2026-06-10T09:14:00',
  admin_remark: 'Forwarded to the examination cell for verification.',
  messages: [{
    sender_role: 'student',
    message_text: 'I requested revaluation of my DBMS paper but the status has not changed in two weeks.',
    created_at: '2026-06-10T09:14:00'
  }, {
    sender_role: 'admin',
    message_text: "We've forwarded your request to the examination cell. You'll hear back within 5 working days.",
    created_at: '2026-06-11T15:02:00'
  }]
}, {
  ticket_id: 1039,
  category: 'Fees & Payments',
  status: 'resolved',
  first_message: 'My fee payment failed but the amount was debited from my account.',
  created_at: '2026-06-08T11:40:00',
  admin_remark: '',
  messages: [{
    sender_role: 'student',
    message_text: 'My fee payment failed but the amount was debited from my account.',
    created_at: '2026-06-08T11:40:00'
  }, {
    sender_role: 'admin',
    message_text: 'The failed transaction has been reversed. The amount will reflect in 3-5 working days. Marking this resolved.',
    created_at: '2026-06-09T10:20:00'
  }]
}, {
  ticket_id: 1021,
  category: 'Hostel & Facilities',
  status: 'closed',
  first_message: 'The Wi-Fi in Block C has been down for three days.',
  created_at: '2026-05-29T18:05:00',
  admin_remark: '',
  feedback_rating: 5,
  messages: [{
    sender_role: 'student',
    message_text: 'The Wi-Fi in Block C has been down for three days.',
    created_at: '2026-05-29T18:05:00'
  }, {
    sender_role: 'admin',
    message_text: 'Network team has restored the Block C access point. Please confirm connectivity.',
    created_at: '2026-05-30T09:30:00'
  }, {
    sender_role: 'student',
    message_text: "It's working now, thank you!",
    created_at: '2026-05-30T12:11:00'
  }]
}];
function hdFmtDate(raw) {
  try {
    const d = new Date(raw);
    return d.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    }) + ' ' + d.toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (_) {
    return raw;
  }
}
window.hdFmtDate = hdFmtDate;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/student/data.js", error: String((e && e.message) || e) }); }

__ds_ns.Button = __ds_scope.Button;

__ds_ns.ChoiceButtons = __ds_scope.ChoiceButtons;

__ds_ns.OptionButton = __ds_scope.OptionButton;

__ds_ns.ChatBubble = __ds_scope.ChatBubble;

__ds_ns.TypingIndicator = __ds_scope.TypingIndicator;

__ds_ns.ThreadMessage = __ds_scope.ThreadMessage;

__ds_ns.KpiCard = __ds_scope.KpiCard;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Skeleton = __ds_scope.Skeleton;

__ds_ns.SkeletonGroup = __ds_scope.SkeletonGroup;

__ds_ns.StarRating = __ds_scope.StarRating;

__ds_ns.StatusBadge = __ds_scope.StatusBadge;

__ds_ns.Toast = __ds_scope.Toast;

__ds_ns.ChoiceTile = __ds_scope.ChoiceTile;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Textarea = __ds_scope.Textarea;

__ds_ns.Tabs = __ds_scope.Tabs;

__ds_ns.Modal = __ds_scope.Modal;

})();
