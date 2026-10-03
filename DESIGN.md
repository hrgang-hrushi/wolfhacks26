# RoadSense AI — Comprehensive Design System & UI/UX Specification

> **Version**: 1.0.0  
> **Target Form Factor**: Edge-to-Edge Responsive Fullscreen Dashboard (`100vw × 100vh`)  
> **Status**: Production Reference Standard  

---

## 1. Executive Summary & Design Vision

RoadSense AI is an intelligent infrastructure and pavement prediction platform designed with an ultra-premium, tactile, and human-centric aesthetic. The interface merges spatial GIS intelligence with real estate and municipal telemetry into a single, cohesive, zero-scroll viewport.

### Core Philosophy
1. **Zero-Scroll Fullscreen Command Center**: The entire dashboard exists within an edge-to-edge `100vw × 100vh` frame. All data, cards, maps, and metrics are visible at a glance without awkward vertical scrollbars.
2. **Tactile Elevation & Soft Surfaces**: Floating cards feature generous corner curvature (`border-radius: 20px`), subtle border definitions (`1px solid rgba(0,0,0,0.06)`), and diffused ambient shadows (`box-shadow: 0 4px 18px rgba(0,0,0,0.04)`).
3. **Decoupled Visual Architecture**: Interactive controls (inputs, dropdowns, buttons) are **never** baked into static raster images. All controls are independent, self-contained HTML/SVG components that dynamically anchor and resize without drifting.
4. **Vibrant Data Accents**: A disciplined neutral palette (#ffffff, #f8fafc, #111827) is accentuated by high-contrast jet black floating chips (#111111) and radiant amber glows (#f59e0b) for active alerts and status pins.

---

## 2. Layout & Viewport Architecture

```
+-----------------------------------------------------------------------------------------------+
| Rail  | Main Pane (flex-direction: column; gap: 10px; padding: 12px 16px 12px 12px)          |
| (76px)| +-----------------------------------------------------------------------------------+ |
|       | | Clean Map Card (flex: 1.25, ~57% viewport height)                                 | |
|       | | [Search Pill] [Insurance Type v] [State v] [City v] [District v]                  | |
|       | |                                                                                   | |
|       | |              (O) Costa Mesa Pin        [15 Houses] [$4.9M Est] [5Y Avg]           | |
|       | +-----------------------------------------------------------------------------------+ |
|       | +-----------------------------------------------------------------------------------+ |
|       | | Bottom Row (flex: 1, ~43% viewport height; display: flex; gap: 10px;)             | |
|       | | +-----------------------+ +-----------------------+ +---------------------------+ | |
|       | | | Location Card         | | Photo Card            | | Tenants & Progress Card   | | |
|       | | | (flex: 1.15)          | | (flex: 0.88)          | | (flex: 0.95)              | | |
|       | | | - Age: 5Y             | | - Architectural Hero  | | - 8.5k Members            | | |
|       | | | - Visitors: 10,742    | | - 20px Curvature      | | - Amber Circular Gauge    | | |
|       | | | - Temp: 29°F          | | - Aspect ratio cover  | | - Multi-avatar stack      | | |
|       | | +-----------------------+ +-----------------------+ +---------------------------+ | |
|       | +-----------------------------------------------------------------------------------+ |
+-----------------------------------------------------------------------------------------------+
```

### Proportions & Sizing Rules
| Zone | Property | Specification |
| :--- | :--- | :--- |
| **Viewport Root** | `width`, `height`, `overflow` | `100vw`, `100vh`, `hidden` (no root scrollbars) |
| **Sidebar Rail** | `width`, `height`, `border-right` | `76px`, `100vh`, `1px solid #eef1f4` |
| **Main Content Pane** | `flex`, `padding`, `gap` | `flex: 1`, `12px 16px 12px 12px`, `gap: 10px` |
| **Top Map Card** | `flex`, `border-radius`, `overflow` | `flex: 1.25` (~57% height), `20px`, `hidden` |
| **Bottom Cards Row** | `flex`, `gap` | `flex: 1` (~43% height), `gap: 10px` |
| **Location Card** | `flex`, `background` | `flex: 1.15`, `#ffffff` |
| **Photo Card** | `flex`, `object-fit` | `flex: 0.88`, `object-fit: cover` |
| **Tenants Card** | `flex`, `background` | `flex: 0.95`, `#ffffff` |

---

## 3. Typography System

The design system uses a geometric neo-grotesque sans-serif with high legibility and warm curves.

### Type Hierarchy
- **Font Family**: `'Plus Jakarta Sans', 'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif`
- **Smoothing**: `-webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;`

| Style Token | Size | Weight | Line Height | Letter Spacing | Example Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Display Hero** | `34px` | 700 (Bold) | `1.0` | `-0.03em` | `8,5k members`, `$4,954.380` |
| **Card Heading** | `20px` | 600 (SemiBold) | `1.2` | `-0.015em` | `Location`, `Tenants` |
| **Metric Large** | `24px` | 600 (SemiBold) | `1.1` | `-0.02em` | `5Y`, `10,742`, `29°F` |
| **Subheading / Meta** | `13px` | 500 (Medium) | `1.35` | `0` | Address lines, Subheaders |
| **Body / Input** | `13.5px` | 400 (Regular) | `1.4` | `0` | Search input, Dropdown items |
| **Pill Filter Labels** | `13px` | 500 (Medium) | `1.2` | `0` | `Insurance Type`, `State`, `City` |
| **Micro Caption** | `11px` | 500 (Medium) | `1.2` | `0.01em` | `House Number`, `Average Age` |

---

## 4. Color Palette & Design Tokens

### CSS Custom Properties
```css
:root {
  /* Surfaces & Backgrounds */
  --bg-dashboard: #ffffff;
  --bg-pane: #f8fafc;
  --bg-card: #ffffff;
  --bg-card-sub: #f0f4f4;
  --sidebar-bg: #ffffff;
  --sidebar-border: #eef1f4;

  /* Typography Colors */
  --text-primary: #111827;     /* High contrast charcoal */
  --text-secondary: #475569;   /* Slate gray for secondary copy */
  --text-muted: #94a3b8;       /* Subtle meta labels */
  --text-inverse: #ffffff;     /* White on dark cards */

  /* Accent & Status */
  --accent-amber: #f59e0b;     /* Primary action & telemetry amber */
  --accent-amber-light: #fbbf24;
  --accent-amber-glow: rgba(245, 158, 11, 0.4);
  --dark-chip-bg: #111111;     /* Contrast black floating badges */

  /* Borders & Shadows */
  --card-border: 1px solid rgba(0, 0, 0, 0.06);
  --pill-border: 1px solid rgba(0, 0, 0, 0.09);
  --card-radius: 20px;
  --pill-radius: 12px;
  --shadow-subtle: 0 4px 18px rgba(0, 0, 0, 0.04);
  --shadow-dropdown: 0 10px 25px -5px rgba(0, 0, 0, 0.12), 0 8px 10px -6px rgba(0, 0, 0, 0.06);
}
```

---

## 5. Component Anatomy & Specifications

### 5.1 Left Sidebar Navigation Rail (`CleanSidebar.tsx`)
- **Container**: `width: 76px; height: 100vh; flex-direction: column; justify-content: space-between; align-items: center; padding: 16px 0 14px;`
- **Branding**:
  - `logo.webp` (38×38px) top icon button.
- **Navigation Cluster**:
  - Active Home Button: Dark pill container (`width: 44px; height: 44px; background: #000000; border-radius: 12px;`) with high-res white icon.
  - Secondary Action Buttons: Crisp SVG icons from `lucide-react` (`Plus`, `Calendar`, `MessageSquare`, `Ticket`, `Settings`) sized at 22px with hover tint `#f1f5f9`.
- **Bottom Section**:
  - Authentic `n_badge.webp` (30×30px) notification badge and circular user settings.

### 5.2 Map Card & Floating Controls (`CleanMapCard.tsx`)
- **Map Backdrop**: High-resolution raster map texture or MapLibre canvas (`object-fit: cover; object-position: top center; border-radius: 20px;`).
- **Top Floating Pill Bar**:
  - `position: absolute; top: 10px; left: 16px; right: 16px; height: 42px; display: flex; gap: 12px; z-index: 20;`
  - **Search Box**:
    - `flex: 1.2; min-width: 200px; max-width: 460px; height: 42px;`
    - White background (`#ffffff`), `border-radius: 12px`, `border: 1px solid rgba(0,0,0,0.09)`.
    - Integrated Lucide `<Search size={16} color="#64748b" />` + clean placeholder `"Search"`.
  - **Filter Buttons**:
    - Labels: `Insurance Type`, `State`, `City`, `District`.
    - Integrated Lucide `<ChevronDown size={14} color="#64748b" />`.
    - Active toggle flips chevron `transform: rotate(180deg)`.
  - **Dropdown Menus**:
    - `position: absolute; top: calc(100% + 6px); left: 0; min-width: 200px;`
    - Solid `#ffffff` background with 12px border radius, shadow `--shadow-dropdown`, and z-index 50.
    - Click-outside event listener automatically dismisses menus when unfocused.
- **Floating Stat Chips (Black Badges)**:
  - Three jet-black cards clustered on the right:
    - Chip 1: `15 House Number`
    - Chip 2: `$4,954.380 Estimate House Price` (wide card)
    - Chip 3: `5Y Average Age`
  - Jet-black background (`#111111`), 16px radius, pure white typography.
- **Amber Glowing Hotspot Pins**:
  - Circular glowing amber pins marking road segments (`Costa Mesa`, `Oak View`, `Quail Hill`, `Northwood`).
  - Subtle breathing pulse animation (`box-shadow: 0 0 0 6px rgba(245, 158, 11, 0.25)`).

### 5.3 Location & Telemetry Card (`CleanLocationCard.tsx`)
- **Header**:
  - Title: `Location` with interactive amber heart favorite button.
  - Subtitle: `789 Costa Mesa, Los Angeles, CA 90210`.
  - Tags & Date: `HO-1 , HO-3, HO-7` and `31 Jan 2025`.
- **Telemetry Pods (3 Columns)**:
  - Pod 1: Building Age (`5Y`) with Calendar icon chip.
  - Pod 2: Daily Visitors (`10,742`) with Eye icon chip.
  - Pod 3: Temperature (`29°F`) with Thermometer icon chip.
  - Surface: Soft muted mint/cyan wash (`#f0f4f4`), 16px radius, crisp dark typography.

### 5.4 Architectural Photo Card (`CleanPhotoCard.tsx`)
- **Visual**: Ultra-sharp modern townhouse architecture.
- **Behavior**: Seamlessly fills `flex: 0.88` container with `border-radius: 20px` and subtle dark inset glow.

### 5.5 Tenants & Progress Card (`CleanTenantsCard.tsx`)
- **Header**: `Tenants` heading with supporting text and an overlapping circular avatar stack.
- **Gauge Graphic**:
  - Prominent amber circular progress arc (`stroke: #f59e0b; stroke-width: 14px;`).
  - Centered hero metric: `8,5k members`.

---

## 6. Interaction & Micro-Animation Standards

1. **Button Hover States**:
   - Background transitions from `#ffffff` to `#f8fafc` (`transition: all 0.15s ease`).
   - Border darkens subtly from `rgba(0,0,0,0.09)` to `rgba(0,0,0,0.18)`.
2. **Dropdown Transitions**:
   - Menu mounts with a 150ms ease-out opacity and scale transition (`transform: translateY(0)` from `-4px`).
   - Chevron icon rotates smoothly 180 degrees.
3. **Map Pin Interactions**:
   - Hovering a map pin enlarges the glowing halo.
   - Clicking a pin synchronizes the telemetry cards and opens the segment inspection drawer.
4. **Click-Outside Architecture**:
   - All dropdowns, drawers, and modal popups must register a global `mousedown` listener to dismiss when clicking on backdrop areas.

---

## 7. Strict "Do's and Don'ts" (Project-Wide Directives)

### ⛔ NEVER DO (Strict Prohibitions)
1. **DON'T bake UI controls into background images**: Never paint text, button borders, search boxes, or chevron arrows into PNG/WEBP raster assets. If a background image contains baked controls, inpaint or remove them so the HTML components are the sole visual layer.
2. **DON'T use invisible transparent hitboxes over static imagery**: Transparent `<button>` overlays will inevitably drift, misalign, or break whenever the viewport aspect ratio or zoom level shifts.
3. **DON'T introduce document scrollbars**: The application is an edge-to-edge command center. `html, body, #root, .fullscreen-dashboard-root` must remain `overflow: hidden; height: 100vh;`.
4. **DON'T use hardcoded pixel widths for fluid cards**: Always use CSS flexbox ratios (`flex: 1.25`, `flex: 1.15`, `flex: 0.88`, `flex: 0.95`) rather than fixed pixel dimensions (`width: 800px`) so the dashboard breathes naturally across all monitor sizes.
5. **DON'T use low-resolution raster icons**: Always prefer SVG icons (such as `lucide-react`) for buttons, chevrons, search indicators, and actions to avoid pixelation on high-DPI displays.

### ✅ ALWAYS DO (Required Practices)
1. **DO style HTML controls with complete visual tokens**: Every button must own its `background`, `border`, `padding`, `border-radius`, typography, and icon layout.
2. **DO position dropdowns relative to their triggers**: Always place dropdowns inside a `.relative` wrapper with `position: absolute; top: calc(100% + 6px); left: 0; min-width: 100%;` so they remain mathematically locked to the button.
3. **DO maintain the 20px card radius standard**: All primary viewport cards (`MapCard`, `LocationCard`, `PhotoCard`, `TenantsCard`) must strictly preserve `border-radius: 20px`.
4. **DO test across viewport sizes**: Verify at standard laptop resolutions (1512×982, 1440×900, 1920×1080) to confirm zero overflow and seamless card proportions.
5. **DO preserve semantic contrast**: Maintain dark text (`#111827`) on light surfaces and pure white (`#ffffff`) on dark badges (`#111111`) for WCAG AA compliance.

---

*This specification governs all frontend development for RoadSense AI across web, mobile, and presentation modules.*
