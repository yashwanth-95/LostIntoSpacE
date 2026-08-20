import { NavLink } from 'react-router-dom';

import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';

/**
 * Navigation, structured around the work rather than around the codebase.
 *
 * The old structure was a list of features — Explore, Catalog, Rocket Lab,
 * Builder, Launch, Mission Control, Assistant, Search — which told a newcomer
 * nothing about what to do or in what order. Worse, Catalog and Explore were
 * two names for the same data, and Rocket Lab and Builder were two doors into
 * the same room.
 *
 * This is the product's actual journey, and the group headings are verbs
 * because each one is a thing you *do*:
 *
 *   EXPLORE   — look at what is out there
 *   UNDERSTAND — learn why it behaves that way
 *   BUILD     — make something
 *   SIMULATE  — fly it under real conditions
 *   EVALUATE  — find out what happened and why
 *
 * A user can start anywhere, and the ordering says what follows what without
 * forcing it. Help sits at the bottom with the workspace because it is
 * infrastructure, not a step.
 */

interface NavItem {
  readonly path: string;
  readonly label: string;
  readonly hint: string;
  readonly icon: (props: { className?: string }) => JSX.Element;
}

interface NavGroup {
  readonly label: string;
  readonly items: readonly NavItem[];
}

const NAV: readonly NavGroup[] = [
  {
    label: 'Explore',
    items: [
      {
        path: '/explore',
        label: 'Space objects',
        hint: 'Planets, moons, spacecraft and small bodies',
        icon: GlobeIcon,
      },
      {
        path: '/missions',
        label: 'Mission library',
        hint: 'Real flights, and what they found',
        icon: FlagIcon,
      },
    ],
  },
  {
    label: 'Understand',
    items: [
      {
        path: '/learn',
        label: 'Science',
        hint: 'Orbital mechanics, propulsion, atmospheric flight',
        icon: BookIcon,
      },
      {
        path: '/experiments',
        label: 'Experiments',
        hint: 'Change one variable and watch what happens',
        icon: FlaskIcon,
      },
    ],
  },
  {
    label: 'Build',
    items: [
      {
        path: '/rocket-lab',
        label: 'Rocket lab',
        hint: 'Start from a preset or from nothing',
        icon: BeakerIcon,
      },
      {
        path: '/builder',
        label: 'Vehicle assembly',
        hint: 'Components, staging, stability',
        icon: WrenchIcon,
      },
    ],
  },
  {
    label: 'Simulate',
    items: [
      {
        path: '/launch',
        label: 'Launch setup',
        hint: 'Site, weather, target orbit',
        icon: PadIcon,
      },
      {
        path: '/mission-control',
        label: 'Flight',
        hint: 'Trajectory and live telemetry',
        icon: GaugeIcon,
      },
    ],
  },
  {
    label: 'Evaluate',
    items: [
      {
        path: '/evaluation',
        label: 'Mission report',
        hint: 'Scores, failures, recommendations',
        icon: ReportIcon,
      },
      {
        path: '/compare',
        label: 'Compare designs',
        hint: 'Two vehicles, side by side',
        icon: CompareIcon,
      },
    ],
  },
];

const BOTTOM: readonly NavItem[] = [
  {
    path: '/workspace',
    label: 'Workspace',
    hint: 'Saved projects and flights',
    icon: FolderIcon,
  },
  {
    path: '/assistant',
    label: 'Assistant',
    hint: 'It can see what you are working on',
    icon: SparklesIcon,
  },
  { path: '/help', label: 'Help desk', hint: 'Documentation and troubleshooting', icon: HelpIcon },
];

export function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggle = useUIStore((s) => s.toggleSidebar);

  return (
    <aside
      className={cn(
        'fixed inset-y-0 left-0 z-chrome flex flex-col bg-[color:var(--plane-1)] hairline-r',
        'transition-[width] duration-settle ease-instrument',
        collapsed ? 'w-14' : 'w-60',
      )}
    >
      <NavLink
        to="/"
        className="flex h-14 shrink-0 items-center gap-2.5 px-4 hairline-b focus-ring"
        title="LostIntoSpacE — home"
      >
        <MarkIcon className="h-5 w-5 shrink-0 text-signal-flame" />
        {!collapsed && (
          <span className="font-display text-lg leading-none text-ink-50">LostIntoSpace</span>
        )}
      </NavLink>

      <nav className="flex-1 overflow-y-auto py-3 no-scrollbar">
        {NAV.map((group) => (
          <div key={group.label} className="mb-4">
            {!collapsed && <p className="px-4 pb-1.5 t-label">{group.label}</p>}
            <ul>
              {group.items.map((item) => (
                <li key={item.path}>
                  <NavItemLink item={item} collapsed={collapsed} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="shrink-0 hairline-t py-2">
        <ul>
          {BOTTOM.map((item) => (
            <li key={item.path}>
              <NavItemLink item={item} collapsed={collapsed} />
            </li>
          ))}
        </ul>

        <button
          onClick={toggle}
          className={cn(
            'mt-1 flex w-full items-center gap-3 px-4 py-2 text-ink-600',
            'transition-colors duration-quick hover:text-ink-300 focus-ring',
          )}
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          <ChevronIcon className={cn('h-4 w-4 shrink-0 transition-transform', collapsed && 'rotate-180')} />
          {!collapsed && (
            <span className="font-condensed text-micro uppercase tracking-instrument">
              Collapse
            </span>
          )}
        </button>
      </div>
    </aside>
  );
}

/**
 * One navigation entry.
 *
 * The active state is a flame-coloured left edge rather than a filled pill —
 * a marker on a rail, matching how the rest of the interface indicates state.
 */
function NavItemLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.path}
      title={collapsed ? `${item.label} — ${item.hint}` : item.hint}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-3 px-4 py-2',
          'transition-colors duration-quick ease-instrument focus-ring',
          isActive ? 'text-ink-50' : 'text-ink-400 hover:text-ink-100',
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={cn(
              'absolute inset-y-1 left-0 w-[2px] transition-colors duration-quick',
              isActive ? 'bg-signal-flame' : 'bg-transparent group-hover:bg-ink-700',
            )}
            aria-hidden="true"
          />
          <Icon className="h-4 w-4 shrink-0" />
          {!collapsed && <span className="truncate text-sm">{item.label}</span>}
        </>
      )}
    </NavLink>
  );
}

// ============================================================
// Icons
//
// Drawn as thin strokes on a 16-unit grid rather than pulled from an icon set:
// a consistent 1.25 weight matches the hairlines the rest of the interface is
// built from, and a filled or rounded icon set would fight it.
// ============================================================

interface IconProps {
  className?: string;
}

function stroke(className?: string) {
  return {
    className,
    viewBox: '0 0 16 16',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.25,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };
}

function MarkIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <circle cx="8" cy="8" r="3.2" />
      <ellipse cx="8" cy="8" rx="7" ry="2.6" transform="rotate(-24 8 8)" />
    </svg>
  );
}

function GlobeIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <circle cx="8" cy="8" r="6" />
      <path d="M2 8h12M8 2c1.8 2 1.8 10 0 12M8 2c-1.8 2-1.8 10 0 12" />
    </svg>
  );
}

function FlagIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M4 14V2.5M4 3h8l-1.6 2.4L12 8H4" />
    </svg>
  );
}

function BookIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M2.5 3.5h4a2 2 0 0 1 2 2v8a1.6 1.6 0 0 0-1.6-1.6H2.5zM13.5 3.5h-4a2 2 0 0 0-2 2v8a1.6 1.6 0 0 1 1.6-1.6h4.4z" />
    </svg>
  );
}

function FlaskIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M6.5 2v4L3 12.2A1.4 1.4 0 0 0 4.2 14h7.6a1.4 1.4 0 0 0 1.2-1.8L9.5 6V2M5.5 2h5M4.6 10h6.8" />
    </svg>
  );
}

function BeakerIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M8 1.5c1.9 1.7 3 4 3 6.4 0 1.6-.4 3-1.1 4.2H6.1A9 9 0 0 1 5 7.9c0-2.4 1.1-4.7 3-6.4Z" />
      <path d="M6.1 12.1 4.6 14.5M9.9 12.1l1.5 2.4" />
      <circle cx="8" cy="6.4" r="1.1" />
    </svg>
  );
}

function WrenchIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M10.6 2.4a3.4 3.4 0 0 0-4.3 4.3l-4 4a1.3 1.3 0 0 0 1.9 1.9l4-4a3.4 3.4 0 0 0 4.3-4.3L10.8 6.2 9 5.8 8.6 4z" />
    </svg>
  );
}

function PadIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M8 1.5c1.6 1.8 2.4 4 2.4 6.3V11H5.6V7.8C5.6 5.5 6.4 3.3 8 1.5Z" />
      <path d="M5.6 8.4 3.6 10.6V13M10.4 8.4l2 2.2V13M2 14.5h12" />
    </svg>
  );
}

function GaugeIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M2.2 12a6.4 6.4 0 1 1 11.6 0" />
      <path d="M8 12 11 6.6" />
      <circle cx="8" cy="12" r="0.9" />
    </svg>
  );
}

function ReportIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M3.5 2h6L12.5 5v9h-9z" />
      <path d="M9.2 2v3.2h3.2M5.8 8.5h4.4M5.8 11h3" />
    </svg>
  );
}

function CompareIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M8 1.6v12.8M4.2 4.5H2v6h2.2zM14 4.5h-2.2v6H14z" />
    </svg>
  );
}

function FolderIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M2 4.2A1.2 1.2 0 0 1 3.2 3h2.6l1.4 1.8h5.6A1.2 1.2 0 0 1 14 6v6a1.2 1.2 0 0 1-1.2 1.2H3.2A1.2 1.2 0 0 1 2 12z" />
    </svg>
  );
}

function SparklesIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M6.2 2.2 7.3 5l2.8 1.1L7.3 7.2 6.2 10 5.1 7.2 2.3 6.1 5.1 5zM11.6 8.6l.6 1.5 1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6z" />
    </svg>
  );
}

function HelpIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <circle cx="8" cy="8" r="6" />
      <path d="M6.4 6.2a1.7 1.7 0 1 1 2.3 1.6c-.5.2-.7.6-.7 1.1v.3" />
      <path d="M8 11.6h.01" />
    </svg>
  );
}

function ChevronIcon({ className }: IconProps) {
  return (
    <svg {...stroke(className)}>
      <path d="M10 4 6 8l4 4" />
    </svg>
  );
}
