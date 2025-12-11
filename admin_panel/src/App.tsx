import React from 'react';

type Role = 'viewer' | 'analyst' | 'operator' | 'admin' | 'superadmin' | 'tenant_owner' | 'ai_trader';

const fakeUser = {
  name: 'Osif',
  role: 'superadmin' as Role,
  tenant: 'SLH Global',
};

const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-slate-50">
      <header className="border-b border-slate-800 bg-slate-950/60 backdrop-blur sticky top-0 z-20">
        <div className="max-w-6xl mx-auto flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-gradient-to-tr from-primary to-accent flex items-center justify-center text-xs font-bold">
              SLH
            </div>
            <div>
              <div className="text-sm uppercase tracking-[0.2em] text-slate-400">
                SLH Finance
              </div>
              <div className="text-lg font-semibold">Investor Control Center</div>
            </div>
          </div>

          <div className="flex items-center gap-4 text-xs">
            <div className="flex flex-col items-end">
              <span className="text-slate-400">Tenant</span>
              <span className="font-medium text-slate-100">{fakeUser.tenant}</span>
            </div>
            <div className="h-10 w-[1px] bg-slate-800" />
            <div className="flex flex-col items-end">
              <span className="text-slate-400">Logged in as</span>
              <span className="font-medium">
                {fakeUser.name} · <span className="uppercase text-accent text-[0.7rem]">{fakeUser.role}</span>
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-8">
        <section className="grid gap-4 md:grid-cols-4">
          <div className="col-span-2 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              TVL & Exposure
            </div>
            <div className="mt-3 text-3xl font-semibold">₪ 1,250,000</div>
            <p className="mt-1 text-xs text-slate-400">
              Total value locked across all investors, wallets and staking pools (demo data).
            </p>
            <div className="mt-4 grid grid-cols-3 gap-3 text-xs">
              <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-3">
                <div className="text-slate-400">Investors</div>
                <div className="mt-1 text-lg font-semibold">37</div>
              </div>
              <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-3">
                <div className="text-slate-400">Active stakes</div>
                <div className="mt-1 text-lg font-semibold">19</div>
              </div>
              <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-3">
                <div className="text-slate-400">Referral SLHA</div>
                <div className="mt-1 text-lg font-semibold">128,400</div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Actions
            </div>
            <button className="w-full rounded-xl bg-primary/80 hover:bg-primary text-sm font-medium py-2.5 transition">
              Add Tenant
            </button>
            <button className="w-full rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs py-2 transition">
              Invite Admin
            </button>
            <button className="w-full rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs py-2 transition">
              Open AI Trading Studio
            </button>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Status
            </div>
            <ul className="text-xs space-y-1 text-slate-300">
              <li>✅ API reachable (Railway)</li>
              <li>✅ Webhook connected (Telegram)</li>
              <li>✅ SLH / SLHA engines online</li>
              <li>🟡 AI suggestions: sandbox mode</li>
            </ul>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Queues & Events
              </div>
              <span className="rounded-full bg-emerald-500/15 text-emerald-300 text-[0.7rem] px-2 py-0.5">
                live stream (demo)
              </span>
            </div>
            <ul className="mt-3 text-xs space-y-1 text-slate-300">
              <li>• Referral bonus credited to user 224223270 (+0.00001 SLH)</li>
              <li>• New stake opened: 10,000 ₪ · 90 days · 14% APY (simulated)</li>
              <li>• AI flagged BNB/USDT as overextended · cool-down suggested</li>
              <li>• Tenant "Family Office Alpha" reached 50,000 ₪ TVL</li>
            </ul>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Roadmap Modules
              </div>
              <span className="text-[0.7rem] text-slate-400">
                Coming soon – already in code as placeholders
              </span>
            </div>
            <ul className="mt-3 text-xs space-y-1 text-slate-300">
              <li>• Staking Engine Pro (multi-pool, lock periods, bonuses)</li>
              <li>• Referral Tree Viewer (Merkle-style)</li>
              <li>• AI Trading Tutor (explains every suggestion in simple language)</li>
              <li>• Investor Academy (multi-language micro lessons)</li>
              <li>• Full SaaS tenants with custom domains</li>
            </ul>
          </div>
        </section>
      </main>
    </div>
  );
};

export default App;
