# AGENTS.md

## Project Identity

RiskRoute is an explainable route-risk intelligence platform. It compares driving routes using historical crash density, severity, route hotspots, driver profile, and time context. The product should feel trustworthy, sharp, modern, and data-driven.

The app is not a generic AI chatbot. It is a geospatial ML product with explainable safety tradeoffs.

## UI Direction

The UI should be modeled after the feel of Mobbin:

* Clean white editorial layout
* Large confident typography
* Minimal but premium navigation
* Spacious sections
* Rounded cards
* Product-preview-first homepage
* Strong search/input focus
* Organized library-like sections
* Clean data cards
* Simple CTAs
* Crisp dividers
* Minimal shadows
* Lots of whitespace
* Smooth but subtle transitions

Do not clone Mobbin exactly. Use it as inspiration for structure, spacing, calmness, and polish.

## Color Palette

Use a mostly white and black interface with one strong safety/risk accent.

Core colors:

* background: #FFFFFF
* foreground: #0A0A0A
* muted foreground: #6B7280
* subtle text: #9CA3AF
* surface: #FFFFFF
* surface subtle: #F8FAFC
* border: #E5E7EB
* border strong: #D1D5DB

Risk colors:

* low risk: #16A34A
* moderate risk: #EAB308
* high risk: #F97316
* very high risk: #DC2626

Brand accent:

* primary: #111827
* primary hover: #000000
* accent: #F97316
* accent soft: #FFF7ED

Map colors:

* safest route: #16A34A
* balanced route: #2563EB
* fastest route: #111827
* hotspot: #DC2626

Avoid generic blue SaaS gradients. The app should feel serious and precise.

## Typography

Do not use Roboto.
Do not use default browser/system styling casually.

Use a clean modern font stack:

* Preferred: Geist Sans
* Fallback: Satoshi, Avenir Next, Helvetica Neue, Arial, sans-serif

Typography hierarchy:

* Display hero: 4.5rem, line-height 1.0, font-weight 650, letter-spacing -0.06em
* H1: 3.5rem, line-height 1.05, font-weight 650, letter-spacing -0.05em
* H2: 2.25rem, line-height 1.1, font-weight 620, letter-spacing -0.035em
* H3: 1.5rem, line-height 1.2, font-weight 600, letter-spacing -0.02em
* Body large: 1.125rem, line-height 1.7, font-weight 400
* Body: 1rem, line-height 1.6, font-weight 400
* Small: 0.875rem, line-height 1.45
* Caption: 0.75rem, line-height 1.35, letter-spacing 0.02em

Use tight heading letter spacing and generous body line-height.

## Spacing Tokens

Use rem-based spacing tokens.

* xs: 0.25rem
* sm: 0.5rem
* md: 0.75rem
* lg: 1rem
* xl: 1.5rem
* 2xl: 2rem
* 3xl: 3rem
* 4xl: 4rem
* 5xl: 6rem
* 6xl: 8rem

Page section spacing:

* mobile section vertical: 4rem
* desktop section vertical: 6rem to 8rem
* page max width: 80rem
* content max width: 68rem
* narrow text max width: 42rem

## Radius

Use consistent border radii:

* small: 0.5rem
* medium: 0.75rem
* large: 1rem
* xl: 1.5rem
* 2xl: 2rem
* full: 9999px

Cards should usually use 1rem to 1.5rem radius.

## Shadows

Use shadows sparingly.

Allowed:

* subtle card shadow: 0 1px 2px rgba(0,0,0,0.04)
* elevated preview shadow: 0 24px 80px rgba(15,23,42,0.08)

Avoid:

* heavy drop shadows
* glowing neon shadows
* generic dashboard shadows everywhere

## Layout Rules

Use:

* CSS Grid
* Flexbox
* Tailwind utility classes
* responsive container classes
* sticky nav
* card grids
* split panels
* large preview panels

Avoid:

* raw manual CSS unless needed
* absolute positioning for normal layout
* table-based layout
* hardcoded pixel-heavy spacing
* cluttered dashboards

## Components

All major UI should be componentized.

Core components:

* Navbar
* Hero
* RouteSearchForm
* DriverProfileSelector
* PreferenceToggleGroup
* RiskMap
* RouteComparison
* RouteCard
* RiskBreakdown
* StatCard
* HotspotList
* ReportSummary

Component style:

* rounded borders
* subtle dividers
* clean labels
* strong empty states
* calm hover states
* accessible focus rings

## Motion

Use subtle transitions:

* hover translate-y: -1px
* opacity transitions
* border color transitions
* scale only for important CTAs
* duration 150ms to 250ms
* ease-out

Avoid:

* bouncing animations
* spinning decorative elements
* excessive parallax
* distracting scroll effects

## What To Avoid

Do not:

* use generic gray gradients
* overuse box shadows
* use Roboto
* make it look like a default shadcn dashboard
* use huge glassmorphism everywhere
* use neon cyberpunk styling
* overuse AI sparkle icons
* center every section
* make every card the same size if hierarchy matters
* make the UI feel like a crypto dashboard
* make risk recommendations sound legally guaranteed
* claim a route is safe with certainty

## Modern CSS Requirements

Lean into:

* Tailwind CSS
* CSS Grid
* Flexbox
* container queries if useful
* responsive typography
* sticky positioning
* backdrop blur only for nav
* logical spacing
* semantic HTML

Do not write large raw CSS files unless unavoidable.

## Accessibility

Use:

* semantic buttons
* labels for inputs
* keyboard focus states
* sufficient color contrast
* aria-labels for icon buttons
* alt text for meaningful imagery
* reduced-motion support if using animation

## Product Copy Tone

Tone should be:

* precise
* calm
* practical
* trustworthy
* not fearmongering

Say:
"Lower-risk based on historical crash patterns."

Do not say:
"This route is safe."
"This route prevents accidents."
"Guaranteed safest route."
