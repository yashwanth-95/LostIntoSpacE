import { Link, useNavigate } from 'react-router-dom';
import { Starfield } from '@/components/features/explore/Starfield';
import { useAuthStore } from '@/stores/authStore';

/**
 * The front door.
 *
 * The brief asks for something cinematic that is not a SaaS dashboard, and the
 * honest way to do that here is depth rather than decoration: a real starfield
 * behind the hero, one clear sentence about what this is, and the actual
 * product loop laid out as the thing you can walk into. No stat counters, no
 * testimonial cards, no gradient soup.
 *
 * "Continue as guest" is given equal weight to signing up, because the whole
 * platform works without an account and pretending otherwise would be a lie
 * told for conversion.
 */

const LOOP = [
  {
    step: '01',
    title: 'Explore',
    body: 'Planets, moons, spacecraft and missions, with the source of every number attached.',
    to: '/explore',
  },
  {
    step: '02',
    title: 'Learn',
    body: 'Propulsion, orbital mechanics, staging — the concepts you need to build something that flies.',
    to: '/learn',
  },
  {
    step: '03',
    title: 'Build',
    body: 'Assemble a rocket from real components. Mass, thrust, delta-v and stability update as you go.',
    to: '/rocket-lab',
  },
  {
    step: '04',
    title: 'Launch',
    body: 'Choose a pad, a target orbit and a guidance program, then run the pre-flight checks.',
    to: '/launch',
  },
  {
    step: '05',
    title: 'Simulate',
    body: 'A Python physics engine flies it: gravity, drag, staging, and the failures your design earns.',
    to: '/mission-control',
  },
  {
    step: '06',
    title: 'Understand',
    body: 'Watch the telemetry, see what went wrong, and get a grounded explanation with sources.',
    to: '/assistant',
  },
];

export default function Landing() {
  const navigate = useNavigate();
  const continueAsGuest = useAuthStore((s) => s.continueAsGuest);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const enterAsGuest = () => {
    continueAsGuest();
    navigate('/explore');
  };

  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <Starfield className="absolute inset-0" density={220} />
        <div
          className="absolute inset-0 bg-gradient-to-b from-transparent via-space-950/40 to-space-950"
          aria-hidden="true"
        />

        <div className="relative mx-auto max-w-4xl px-6 py-28 md:py-36 text-center">
          <p className="text-2xs md:text-xs uppercase tracking-[0.35em] text-accent-cyan/80 mb-6">
            Learn · Build · Simulate · Explore
          </p>

          <h1 className="font-display text-4xl md:text-6xl font-bold text-space-50 leading-[1.1] mb-6">
            You are not reading about space.
            <br />
            <span className="text-gradient">You are exploring it.</span>
          </h1>

          <p className="text-base md:text-lg text-space-300 max-w-2xl mx-auto leading-relaxed mb-10">
            LostIntoSpace is a space laboratory in your browser. Study real objects and
            missions, learn the engineering, build a rocket from real components, then fly it
            through a physics simulation that tells you the truth about your design.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/rocket-lab"
              className="h-11 px-6 inline-flex items-center rounded-md text-sm font-medium bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/40 hover:bg-accent-cyan/25 transition-colors glow-cyan focus-ring"
            >
              Build a rocket
            </Link>
            <Link
              to="/explore"
              className="h-11 px-6 inline-flex items-center rounded-md text-sm font-medium bg-space-800/80 text-space-100 border border-space-700 hover:bg-space-700 transition-colors focus-ring"
            >
              Explore space
            </Link>
            {!isAuthenticated && (
              <button
                onClick={enterAsGuest}
                className="h-11 px-6 inline-flex items-center rounded-md text-sm text-space-400 hover:text-space-100 transition-colors focus-ring"
              >
                Continue as guest →
              </button>
            )}
          </div>

          <p className="mt-6 text-2xs text-space-600">
            No account needed. Signing in saves your designs, missions and progress.
          </p>
        </div>
      </section>

      {/* The loop */}
      <section className="mx-auto max-w-6xl px-6 py-20">
        <div className="mb-12 max-w-2xl">
          <h2 className="font-display text-2xl md:text-3xl font-semibold text-space-100 mb-3">
            One continuous loop, not six disconnected tools
          </h2>
          <p className="text-sm text-space-400 leading-relaxed">
            Everything you learn feeds the thing you build; everything you build gets flown;
            every flight gives you something to understand. You can start anywhere.
          </p>
        </div>

        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {LOOP.map((item) => (
            <li key={item.step}>
              <Link
                to={item.to}
                className="group block h-full glass-panel p-5 hover:border-accent-cyan/40 transition-colors focus-ring"
              >
                <div className="flex items-baseline gap-3 mb-2">
                  <span className="font-mono text-2xs text-accent-cyan/70">{item.step}</span>
                  <h3 className="font-display text-base font-semibold text-space-100 group-hover:text-accent-cyan transition-colors">
                    {item.title}
                  </h3>
                </div>
                <p className="text-xs text-space-400 leading-relaxed">{item.body}</p>
              </Link>
            </li>
          ))}
        </ol>
      </section>

      {/* Honesty panel — the brief is explicit that approximations must be stated */}
      <section className="mx-auto max-w-6xl px-6 pb-20">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="glass-panel p-5">
            <h3 className="font-display text-sm font-semibold text-space-100 mb-2">
              Real physics, honestly labelled
            </h3>
            <p className="text-xs text-space-400 leading-relaxed">
              RK4 integration, inverse-square gravity, the US Standard Atmosphere, transonic
              drag rise, staging and mass flow from actual specific impulse. It is an
              educational simulation with documented approximations — never presented as
              flight-certified engineering.
            </p>
          </div>
          <div className="glass-panel p-5">
            <h3 className="font-display text-sm font-semibold text-space-100 mb-2">
              Sourced, not invented
            </h3>
            <p className="text-xs text-space-400 leading-relaxed">
              Object and mission data carries its provenance. The assistant answers from
              retrieved evidence and cites it — and says so when the corpus has nothing,
              rather than making something up.
            </p>
          </div>
          <div className="glass-panel p-5">
            <h3 className="font-display text-sm font-semibold text-space-100 mb-2">
              Failure is the lesson
            </h3>
            <p className="text-xs text-space-400 leading-relaxed">
              A rocket that cannot lift its own weight will not lift off, and the simulation
              will tell you exactly why, at which second, against which threshold — with a
              fix you can go and apply.
            </p>
          </div>
        </div>
      </section>

      {/* Close */}
      <section className="border-t border-space-800/60">
        <div className="mx-auto max-w-4xl px-6 py-16 text-center">
          <h2 className="font-display text-2xl font-semibold text-space-100 mb-3">
            Start with a rocket that fails
          </h2>
          <p className="text-sm text-space-400 mb-8 max-w-xl mx-auto leading-relaxed">
            It is the fastest way to learn what a thrust-to-weight ratio actually means. Build
            one in a few minutes, fly it, and find out.
          </p>
          <Link
            to="/rocket-lab"
            className="h-11 px-6 inline-flex items-center rounded-md text-sm font-medium bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/40 hover:bg-accent-cyan/25 transition-colors focus-ring"
          >
            Open Rocket Lab
          </Link>
        </div>
      </section>
    </div>
  );
}
