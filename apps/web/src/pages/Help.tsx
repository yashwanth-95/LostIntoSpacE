import { Link, useParams } from 'react-router-dom';
import { Card } from '@/components/ui';
import { cn } from '@/lib/utils';

/**
 * Help, guide, FAQ and contact.
 *
 * One page with sections rather than four routes, because the content is short
 * and someone looking for "how do I make my rocket reach orbit" should not have
 * to guess whether that lives under Guide or FAQ. `/help/:topic` scrolls to a
 * section so the footer links still deep-link.
 */

const SECTIONS = [
  { id: 'getting-started', label: 'Getting started' },
  { id: 'guide', label: 'Platform guide' },
  { id: 'simulation', label: 'About the simulation' },
  { id: 'faq', label: 'FAQ' },
  { id: 'troubleshooting', label: 'Troubleshooting' },
  { id: 'contact', label: 'Contact' },
];

export default function Help() {
  const { topic } = useParams();

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-8">
        <h1 className="font-display text-2xl font-semibold text-space-100 mb-2">Help</h1>
        <p className="text-sm text-space-400">
          What this platform is, how to use it, and what it does and does not claim.
        </p>
      </header>

      <nav className="flex flex-wrap gap-1.5 mb-8" aria-label="Help sections">
        {SECTIONS.map((section) => (
          <a
            key={section.id}
            href={`#${section.id}`}
            className={cn(
              'px-2.5 py-1 rounded-md text-2xs border transition-colors focus-ring',
              topic === section.id
                ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
                : 'bg-space-800/50 text-space-400 border-space-700 hover:text-space-200',
            )}
          >
            {section.label}
          </a>
        ))}
      </nav>

      <div className="space-y-8">
        <Section id="getting-started" title="Getting started">
          <p>
            You do not need an account. Choose <em>Continue as guest</em> and everything except
            saving works.
          </p>
          <p>The shortest path to something interesting takes about five minutes:</p>
          <ol className="list-decimal list-inside space-y-1 text-space-400">
            <li>
              Open <Link to="/rocket-lab" className="text-accent-cyan hover:underline">Rocket Lab</Link>{' '}
              and choose the <strong className="text-space-300">Orbital Launcher</strong> preset.
            </li>
            <li>Look at the metrics in the Builder — launch mass, Δv, thrust-to-weight.</li>
            <li>Press <strong className="text-space-300">Configure launch</strong>, pick a target orbit, and launch.</li>
            <li>Watch it fly in Mission Control, then scrub the timeline to any event.</li>
          </ol>
          <p>
            Then try the <strong className="text-space-300">Too Heavy To Fly</strong> preset and
            watch it fail. Reading the failure record is the fastest way to understand what
            thrust-to-weight actually means.
          </p>
        </Section>

        <Section id="guide" title="Platform guide">
          <Definition term="Explore &amp; Catalog">
            Browse catalogued objects — planets, moons, asteroids, spacecraft. Every figure keeps
            the source it came from. Needs the database to be configured.
          </Definition>
          <Definition term="Learn">
            Engineering concepts grouped into paths. Available with no database and no network:
            the content is bundled.
          </Definition>
          <Definition term="Rocket Lab">
            The component catalogue. Every mass, thrust and specific-impulse figure here is the
            one the simulation will use — there is no second set of numbers.
          </Definition>
          <Definition term="Rocket Builder">
            Assemble stages and components. Mass, Δv, thrust-to-weight and static stability
            recompute on every change, and validation tells you what is wrong before you fly.
          </Definition>
          <Definition term="Launch">
            Pick a launch site, a target orbit and a guidance program, then run the pre-flight
            checks. A failing check does not block launch — flying a rocket you were warned about
            is a legitimate way to learn.
          </Definition>
          <Definition term="Mission Control">
            The flight, replayed. 3D view, live telemetry, the event timeline, and the mission
            summary. Playback speed is independent of frame rate.
          </Definition>
          <Definition term="AI Assistant">
            Answers from the platform's knowledge corpus with sources attached. After a failed
            flight it can analyse that specific flight using its telemetry.
          </Definition>
        </Section>

        <Section id="simulation" title="About the simulation">
          <p>
            The flight is computed by a Python physics engine on the server: RK4 integration,
            inverse-square gravity, the US Standard Atmosphere 1976, transonic drag rise,
            altitude-compensated thrust, real mass flow from specific impulse, staging, guidance
            and failure detection.
          </p>
          <p className="text-severity-warning">
            It is an educational simulation, not flight-certified engineering software.
          </p>
          <p>Known simplifications, in full:</p>
          <ul className="list-disc list-inside space-y-1 text-space-400">
            <li>3 degrees of freedom — translation only, no rotational dynamics.</li>
            <li>Non-rotating Earth: an eastward launch does not gain the ~465 m/s it would in reality.</li>
            <li>Spherical Earth — no WGS-84 flattening, no J2 perturbation.</li>
            <li>A static average atmosphere — no weather, no seasonal or latitude variation.</li>
            <li>A single drag coefficient per vehicle with a shape-agnostic Mach curve.</li>
            <li>No thermal modelling; the heating limit is a speed-and-altitude threshold, not a computed skin temperature.</li>
          </ul>
          <p>
            The full list lives in <code className="text-space-300">docs/simulation/ASSUMPTIONS.md</code>.
            A simulated failure is never a claim about a real vehicle or a real accident.
          </p>
        </Section>

        <Section id="faq" title="FAQ">
          <Definition term="Why did my rocket not reach orbit?">
            Almost always one of three things: not enough Δv for the target, a guidance program
            that never pitched over (vertical flight cannot reach orbit however high it goes), or
            a thrust-to-weight below 1 so it never left the pad. The Launch page's pre-flight
            checks name which.
          </Definition>
          <Definition term="Why is my Δv budget enough but it still fell short?">
            The ideal Δv from the rocket equation is before losses. Gravity typically takes about
            1.5 km/s on an Earth ascent and drag another 50–150 m/s. Mission Control's summary
            shows both for your flight.
          </Definition>
          <Definition term="Do I need an account?">
            No. Guest mode covers the entire product. An account persists your designs, missions,
            simulations and learning progress.
          </Definition>
          <Definition term="Is the AI making things up?">
            It answers from retrieved passages and cites them. When the corpus has nothing
            relevant it says so instead of inventing an answer. If no language model is
            configured, the server falls back to an extractive provider and the assistant page
            labels that.
          </Definition>
          <Definition term="Where does the object data come from?">
            NASA, JPL, ESA, ISRO, CelesTrak, the Minor Planet Center and the Exoplanet Archive,
            normalised into one model with provenance retained per record. Bundled reference data
            is labelled as such.
          </Definition>
        </Section>

        <Section id="troubleshooting" title="Troubleshooting">
          <Definition term="Explore or Catalog shows a setup panel">
            The API cannot reach PostgreSQL. The panel lists the exact commands. Everything that
            does not need stored data keeps working.
          </Definition>
          <Definition term="“Could not reach the API”">
            The backend is not running. Start it with{' '}
            <code className="text-space-300">python -m uvicorn src.main:app --reload --port 8000</code>{' '}
            from <code className="text-space-300">apps/api/</code>.
          </Definition>
          <Definition term="Search or the assistant returns 503">
            The server could not import the search or AI engine. Check{' '}
            <code className="text-space-300">/api/v1/health/engines</code>, which reports which
            engine failed and why.
          </Definition>
          <Definition term="A simulation times out">
            Runs are capped at 30 seconds. Shorten the mission or use a coarser timestep;{' '}
            <code className="text-space-300">/api/v1/simulations/limits</code> publishes the caps.
          </Definition>
        </Section>

        <Section id="contact" title="Contact">
          <p>
            LostIntoSpace is an open educational project. Issues, questions and corrections —
            especially corrections to scientific content — are welcome on the repository.
          </p>
          <p>
            <a
              href="https://github.com/yashwanth-95/LostIntoSpacE"
              target="_blank"
              rel="noreferrer noopener"
              className="text-accent-cyan hover:underline"
            >
              github.com/yashwanth-95/LostIntoSpacE
            </a>
          </p>
          <p className="text-space-500">
            For contributor setup see <code className="text-space-300">docs/getting-started/LOCAL_SETUP.md</code>{' '}
            and <code className="text-space-300">docs/contributing/CONTRIBUTOR_GUIDE.md</code>.
          </p>
        </Section>
      </div>
    </div>
  );
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="scroll-mt-20">
      <h2
        id={`${id}-heading`}
        className="font-display text-lg font-semibold text-space-100 mb-3"
      >
        {title}
      </h2>
      <Card className="space-y-3 text-xs text-space-300 leading-relaxed">{children}</Card>
    </section>
  );
}

function Definition({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-space-100 mb-0.5">{term}</h3>
      <p className="text-xs text-space-400 leading-relaxed">{children}</p>
    </div>
  );
}
