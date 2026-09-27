/* SahkarSetu icons — monochrome inline SVG (stroke, currentColor). No emoji. */
const ICON_PATHS = {
  bulb: '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10c.6.6 1 1.2 1 2h6c0-.8.4-1.4 1-2a6 6 0 0 0-4-10z"/>',
  droplet: '<path d="M12 2.7s-6.5 7-6.5 11a6.5 6.5 0 0 0 13 0c0-4-6.5-11-6.5-11z"/>',
  tool: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  brush: '<path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><path d="M2 2l7.586 7.586"/><circle cx="11" cy="11" r="2"/>',
  wind: '<path d="M9.59 4.59A2 2 0 1 1 11 8H2"/><path d="M12.59 19.41A2 2 0 1 0 14 16H2"/><path d="M17.73 7.73A2.5 2.5 0 1 1 19.5 12H2"/>',
  snow: '<path d="M12 2v20"/><path d="M4.9 4.9l14.2 14.2"/><path d="M19.1 4.9L4.9 19.1"/><path d="M2 12h20"/>',
  car: '<path d="M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11"/><path d="M3 11h18v5a1 1 0 0 1-1 1h-1.5"/><path d="M5.5 17H4a1 1 0 0 1-1-1v-5"/><circle cx="7.5" cy="16.5" r="1.8"/><circle cx="16.5" cy="16.5" r="1.8"/><path d="M9.3 17h5.4"/>',
  leaf: '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>',
  pot: '<path d="M4 11h16v3a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5v-3z"/><path d="M8 8V6"/><path d="M12 8V4"/><path d="M16 8V6"/>',
  heart: '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
  bug: '<path d="M12 8a4 4 0 0 1 4 4v3a4 4 0 0 1-8 0v-3a4 4 0 0 1 4-4z"/><path d="M12 8V5"/><path d="M9 5L7 3"/><path d="M15 5l2-2"/><path d="M8 12H4"/><path d="M20 12h-4"/><path d="M8 16l-3 2"/><path d="M16 16l3 2"/>',
  bolt: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" fill="currentColor" stroke="none"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  pin: '<path d="M21 10c0 7-9 12-9 12s-9-5-9-12a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  receipt: '<path d="M4 2h16v20l-2.7-1.8L14.6 22l-2.6-1.8L9.4 22l-2.7-1.8L4 22z"/><path d="M8 7h8"/><path d="M8 11h8"/><path d="M8 15h5"/>',
  star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26"/>',
  warn: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  chart: '<path d="M3 3v18h18"/><path d="M8 17V9"/><path d="M13 17V5"/><path d="M18 17v-7"/>',
  card: '<rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/>',
  award: '<circle cx="12" cy="8" r="6"/><path d="M8.5 13.5L7 22l5-3 5 3-1.5-8.5"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  check: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>',
  rupee: '<path d="M6 3h12"/><path d="M6 8h12"/><path d="M6 13c6 0 8-2.5 8-5"/><path d="M6 13l8 8"/>'
};
function ic(name, size){
  const s = size || 16;
  const body = ICON_PATHS[name] || ICON_PATHS.tool;
  return `<svg class="ic" width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" ` +
         `stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ` +
         `aria-hidden="true">${body}</svg>`;
}
