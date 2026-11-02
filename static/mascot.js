const C = {
  skin: "#edb892", skinShade: "#d99a76", hair: "#1d2b2a", hoodie: "#003c32",
  hood: "#0e5345", string: "#bec8d2", eye: "#1d2b2a", mouth: "#7a3b2e",
  blush: "#f09c86", gray: "#e6e6e6", blue: "#bec8d2",
};

export const MOODS = ["idle", "thinking", "talking", "happy", "wave", "camera", "snap"];

export function mascotSVG(extraClass = "") {
  return `
<svg class="mascot mood-idle ${extraClass}" viewBox="0 0 240 240" role="img" aria-label="Sherlock, asisten virtual">
  <g class="think-bubble" fill="${C.blue}">
    <circle class="tb tb1" cx="62" cy="56" r="5"/>
    <circle class="tb tb2" cx="48" cy="40" r="7"/>
    <g class="tb tb3"><circle cx="34" cy="18" r="15"/>
      <text x="34" y="24" text-anchor="middle" font-size="18" font-weight="700" fill="${C.hoodie}" font-family="sans-serif">?</text></g>
  </g>

  <g class="figure">
    <!-- body -->
    <path d="M28 240 C30 196 62 170 120 170 C178 170 210 196 212 240 Z" fill="${C.hoodie}"/>
    <path d="M78 176 C92 202 148 202 162 176 C150 166 90 166 78 176 Z" fill="${C.hood}"/>
    <path d="M104 140 L136 140 L138 178 C128 188 112 188 102 178 Z" fill="${C.skinShade}"/>
    <path d="M108 194 L106 216 M132 194 L134 216" stroke="${C.string}" stroke-width="3.5" stroke-linecap="round"/>
    <circle cx="106" cy="218" r="3" fill="${C.string}"/><circle cx="134" cy="218" r="3" fill="${C.string}"/>

    <!-- head -->
    <g class="head">
      <ellipse cx="80" cy="104" rx="9" ry="12" fill="${C.skin}"/>
      <ellipse cx="160" cy="104" rx="9" ry="12" fill="${C.skin}"/>
      <ellipse cx="120" cy="100" rx="41" ry="47" fill="${C.skin}"/>
      <path d="M79 98 C74 60 98 40 126 42 C156 44 170 66 163 98 C160 84 152 74 140 72 C134 60 112 58 100 66 C90 72 84 84 79 98 Z" fill="${C.hair}"/>
      <path d="M98 52 C106 28 142 26 152 44 C140 37 122 39 112 54 Z" fill="${C.hair}"/>
      <g class="blush" fill="${C.blush}" opacity=".55">
        <ellipse cx="95" cy="119" rx="7" ry="4"/><ellipse cx="145" cy="119" rx="7" ry="4"/>
      </g>
      <g class="brows" stroke="${C.hair}" stroke-width="3.5" stroke-linecap="round" fill="none">
        <path d="M96 88 Q104 83 112 87"/><path d="M128 87 Q136 83 144 88"/>
      </g>
      <g class="eyes eyes-open" fill="${C.eye}">
        <ellipse cx="104" cy="102" rx="4" ry="5"/><ellipse cx="136" cy="102" rx="4" ry="5"/>
      </g>
      <g class="eyes eyes-happy" stroke="${C.eye}" stroke-width="3" stroke-linecap="round" fill="none">
        <path d="M99 104 Q104 97 109 104"/><path d="M131 104 Q136 97 141 104"/>
      </g>
      <path d="M120 106 Q116 116 121 118" stroke="${C.skinShade}" stroke-width="2.5" stroke-linecap="round" fill="none"/>
      <path class="mouth mouth-neutral" d="M110 128 Q120 132 130 128" stroke="${C.mouth}" stroke-width="3" stroke-linecap="round" fill="none"/>
      <path class="mouth mouth-think" d="M111 131 Q119 126 130 129" stroke="${C.mouth}" stroke-width="3" stroke-linecap="round" fill="none"/>
      <path class="mouth mouth-smile" d="M105 123 Q120 142 135 123 Q120 131 105 123 Z" fill="${C.mouth}"/>
      <ellipse class="mouth mouth-talk" cx="120" cy="129" rx="8" ry="6" fill="${C.mouth}"/>
    </g>

    <!-- thinking: hand scratching the head -->
    <g class="arm-think">
      <path d="M184 198 Q216 150 202 116" stroke="${C.hoodie}" stroke-width="26" stroke-linecap="round" fill="none"/>
      <g class="hand-scratch">
        <path d="M202 116 Q188 88 170 76" stroke="${C.hoodie}" stroke-width="24" stroke-linecap="round" fill="none"/>
        <circle cx="164" cy="70" r="14" fill="${C.skin}"/>
        <path d="M156 62 Q162 58 170 60 M154 70 Q160 66 168 68" stroke="${C.skinShade}" stroke-width="2" stroke-linecap="round" fill="none"/>
      </g>
    </g>

    <!-- waving hello -->
    <g class="arm-wave">
      <path d="M58 198 Q26 168 34 132" stroke="${C.hoodie}" stroke-width="26" stroke-linecap="round" fill="none"/>
      <g class="hand-wave">
        <path d="M34 132 L40 96" stroke="${C.hoodie}" stroke-width="24" stroke-linecap="round" fill="none"/>
        <ellipse cx="41" cy="82" rx="13" ry="15" fill="${C.skin}"/>
        <path d="M31 72 L28 62 M38 68 L37 57 M45 68 L46 57 M51 73 L55 64" stroke="${C.skin}" stroke-width="6" stroke-linecap="round"/>
      </g>
    </g>

    <!-- holding a camera -->
    <g class="camera-rig">
      <path d="M84 226 L92 162 M156 226 L148 162" stroke="${C.hoodie}" stroke-width="24" stroke-linecap="round"/>
      <rect x="100" y="104" width="22" height="10" rx="3" fill="${C.gray}"/>
      <rect x="80" y="110" width="80" height="54" rx="12" fill="${C.gray}" stroke="${C.hoodie}" stroke-width="3"/>
      <circle cx="120" cy="137" r="18" fill="${C.hoodie}"/>
      <circle cx="120" cy="137" r="11" fill="${C.blue}"/>
      <circle cx="115" cy="132" r="3.5" fill="#fff"/>
      <rect x="142" y="117" width="10" height="6" rx="2" fill="#fff"/>
      <circle cx="88" cy="160" r="11" fill="${C.skin}"/><circle cx="152" cy="160" r="11" fill="${C.skin}"/>
      <g class="flash" fill="#fff">
        <path d="M147 90 L151 106 L166 110 L151 114 L147 130 L143 114 L128 110 L143 106 Z"/>
      </g>
    </g>
  </g>
</svg>`;
}

export function setMood(target, mood) {
  const svgs = target.matches?.("svg.mascot") ? [target] : target.querySelectorAll("svg.mascot");
  for (const svg of svgs) {
    MOODS.forEach((m) => svg.classList.remove(`mood-${m}`));
    svg.classList.add(`mood-${mood}`);
  }
}

export function mountMascots(root = document) {
  root.querySelectorAll("[data-mascot]").forEach((el) => {
    const value = el.dataset.mascot || "";
    el.innerHTML = mascotSVG(value === "mini" ? "mini" : "");
    if (MOODS.includes(value)) setMood(el, value);
  });
}
