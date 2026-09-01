---
name: Maiku Signal Garden
description: An interactive field guide for a shared intelligence runtime.
colors:
  runtime-moss: "#0b1f1b"
  runtime-deep: "#0e2923"
  specimen-paper: "#e5ecdc"
  signal-lime: "#c8ff54"
  consequence-coral: "#ff7848"
  artifact-sky: "#8ec5e8"
  quiet-foliage: "#9eb2a4"
typography:
  display:
    fontFamily: "ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(27px, 3.1vw, 49px)"
    fontWeight: 650
    lineHeight: 1.04
    letterSpacing: "-0.045em"
  body:
    fontFamily: "ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    lineHeight: 1.55
  label:
    fontFamily: "ui-sans-serif, system-ui, sans-serif"
    fontSize: "10px"
    fontWeight: 700
    letterSpacing: "0.12em"
rounded:
  control: "8px"
  node: "50%"
spacing:
  tight: "8px"
  control: "12px"
  panel: "20px"
  section: "42px"
components:
  button-primary:
    backgroundColor: "{colors.signal-lime}"
    textColor: "{colors.runtime-moss}"
    padding: "15px 19px"
  participant-row:
    backgroundColor: "rgba(200,255,84,.08)"
    textColor: "#f3f6ea"
    rounded: "{rounded.control}"
    padding: "9px 7px"
---

# Design System: Maiku Signal Garden

## Overview

**Creative North Star: "The Signal Garden."**

Maiku is an operating surface for heterogeneous intelligence, so its interface treats every participant as a living specimen in one shared field. Moss-dark runtime space carries the work; a pale inspection surface reveals exact native capabilities; acid-green traces show permitted connection and motion; coral marks the moments that require human judgment.

The system is technical without code-costume: labels may be compact and operational, but the main reading voice is an approachable sans. Expression serves orientation first. A human approval is visually consequential without becoming alarmist.

**Key Characteristics:** dark field and pale inspector; circular participant nodes; thin luminous connection geometry; exact SVG iconography; flat panels with state-driven glow.

## Colors

The palette is a restrained dark field with one active signal and two semantic exceptions.

### Primary

- **Signal Lime** (`#c8ff54`): active controls, ready state, connection paths, and selected participant outlines.

### Secondary

- **Consequence Coral** (`#ff7848`): human attention, irreversible actions, and blocked or approval states.
- **Artifact Sky** (`#8ec5e8`): artifact-aware capability and completed-record emphasis.

### Neutral

- **Runtime Moss** (`#0b1f1b`): primary operating ground.
- **Runtime Deep** (`#0e2923`): trace region and secondary depth plane.
- **Specimen Paper** (`#e5ecdc`): inspection and focused detail surface.
- **Quiet Foliage** (`#9eb2a4`): secondary copy on the dark field.

**The Signal Rule.** Lime is a behavior signal, not decorative trim: it identifies what is selected, allowed, or ready to run.

## Typography

**Display Font:** `ui-sans-serif, system-ui, sans-serif`.
**Body Font:** `ui-sans-serif, system-ui, sans-serif`.
**Label/Mono Font:** `ui-monospace, SFMono-Regular, monospace` only for affordance and schema-like data.

**Character:** Direct, compact, and readable at operational speed. Large headlines use a tight sans silhouette; labels use uppercase tracking to establish a quiet instrument rhythm.

### Hierarchy

- **Display** (650, `clamp(27px, 3.1vw, 49px)`, 1.04): the one-sentence product truth.
- **Headline** (650, 22–28px, 1.1): selected participant and trace headings.
- **Body** (400, 13–15px, 1.45–1.55): explanations and event text.
- **Label** (700, 9–10px, `0.12em`, uppercase): panel names, statuses, and event kinds.

## Layout

Desktop uses a three-part operating field: fixed participant rail, fluid constellation, and fixed specimen inspector. The trace is a full-width continuation below it. The main shell caps at 1540px; panels align to 20px internal rhythm with 42px outer section spacing.

At 920px the inspector joins a second row. At 680px the workspace becomes a single vertical narrative: participant tray, constellation, then inspector. Circular map nodes stay legible rather than shrinking into a dense graph.

## Elevation & Depth

Depth is tonal and functional. The runtime field layers dark moss planes; the inspector changes to specimen paper; the active shared task receives a restrained lime halo. Shadows only appear under the modal and hoverable task seed, where lifted focus matters.

## Shapes

Controls are crisp rectangles or 8px control forms. Participants and the shared task use circles because they are peers in the runtime, not cards in a dashboard. Borders are thin, translucent, and used to make state boundaries legible rather than to create nested containers.

## Components

### Buttons

- **Primary:** Signal Lime on Runtime Moss, 15px × 19px padding, strong dark text.
- **Quiet:** transparent dark-field control with a 1px translucent border.
- **Focus:** 2px Signal Lime outline with 3px offset.

### Participant Rows

- **Shape:** 8px row with a circular native-kind glyph.
- **State:** selection uses a low-opacity lime field and lime border; status is always shown as a color-coded dot plus nearby text.

### Inspector

- **Character:** a pale specimen-paper contrast plane for reading a selected participant.
- **Content:** identity, description, native affordances, and current grant in that order.

### Signal Constellation

- **Character:** SVG connection lines and orbiting buttons around a central shared task.
- **Behavior:** participants remain semantic buttons; the central task launches the guided trace.

### Human Approval

- **Character:** dark contained decision surface inside the pale inspector.
- **Behavior:** coral names consequence; explicit approve and decline actions preserve human agency.

## Do's and Don'ts

### Do:

- **Do** show a participant's native affordances before inviting a generic prompt.
- **Do** use lime for active or permitted runtime state and coral for human consequence.
- **Do** make the human visually peer-level with every model and tool.
- **Do** keep connections as precise SVG geometry and controls as semantic HTML.

### Don't:

- **Don't** replace the shared runtime map with dashboard metrics or generic cards.
- **Don't** use emoji or mixed icon families; use the thin-stroke SVG system.
- **Don't** flatten every participant into a chat bubble or invent live-integration claims in a demo.
- **Don't** add ambient gradients, glass panels, or decorative motion that weakens operational reading.
