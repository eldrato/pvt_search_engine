'use client';

import { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  Database, 
  Search, 
  Cpu, 
  Layers, 
  Activity, 
  CheckCircle2, 
  AlertTriangle, 
  XCircle, 
  RefreshCw,
  Server,
  Lock
} from 'lucide-react';

interface ServiceHealth {
  status: 'healthy' | 'degraded' | 'unreachable';
  latency_ms: number;
  details: Record<string, any>;
}

interface SystemHealth {
  status: string;
  version: string;
  environment: string;
  services: {
    postgres?: ServiceHealth;
    opensearch?: ServiceHealth;
    qdrant?: ServiceHealth;
    redis?: ServiceHealth;
  };
}

export default function AegisDashboard() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');

  const fetchHealth = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/v1/health');
      if (res.ok) {
        const data: SystemHealth = await res.json();
        setHealth(data);
      } else {
        setHealth(null);
      }
    } catch (err) {
      console.error('Failed to fetch system health:', err);
      setHealth(null);
    } finally {
      setLoading(false);
      setLastRefreshed(new Date());
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case 'healthy':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" /> Healthy
          </span>
        );
      case 'degraded':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertTriangle className="w-3.5 h-3.5" /> Degraded
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <XCircle className="w-3.5 h-3.5" /> Unreachable
          </span>
        );
    }
  };

  return (
    <main className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Glass Header */}
      <header className="sticky top-0 z-50 glass-panel border-b border-slate-800/80 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-lg tracking-tight text-white">AEGIS</h1>
              <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 font-mono">
                v0.1.0-Phase0
              </span>
            </div>
            <p className="text-xs text-slate-400">Privacy-First Personal Search & Research Engine</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-900/60 px-3 py-1.5 rounded-lg border border-slate-800">
            <Lock className="w-3.5 h-3.5 text-emerald-400" />
            <span>Local Privacy Sandbox</span>
          </div>

          <button
            onClick={fetchHealth}
            disabled={loading}
            className="flex items-center gap-2 text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3.5 py-1.5 rounded-lg font-medium transition-all shadow-lg shadow-indigo-600/20 disabled:opacity-50"
            id="refresh-health-btn"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="max-w-6xl mx-auto w-full px-6 py-10 flex-1 flex flex-col gap-10">
        
        {/* Search Input Preview Banner */}
        <div className="glass-panel p-8 rounded-2xl border border-indigo-500/20 shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none animate-glow" />
          
          <div className="max-w-2xl mx-auto text-center flex flex-col gap-4 relative z-10">
            <h2 className="text-3xl font-extrabold tracking-tight text-white">
              Search across your personal intelligence
            </h2>
            <p className="text-sm text-slate-400">
              Hybrid BM25 keyword matching, local vector semantic search, and evidence-backed AI research synthesis.
            </p>

            <div className="relative mt-4">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Ask Aegis or search documents, code, notes... (Phase 1 active soon)"
                className="w-full bg-slate-950/80 border border-slate-700/80 rounded-xl py-3.5 pl-12 pr-4 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all shadow-inner"
              />
            </div>
          </div>
        </div>

        {/* Operational Infrastructure Grid */}
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-indigo-400" />
              <h3 className="font-semibold text-slate-200">Storage Infrastructure Health</h3>
            </div>
            {lastRefreshed && (
              <span className="text-xs text-slate-500">
                Last checked: {lastRefreshed.toLocaleTimeString()}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            
            {/* PostgreSQL SSOT */}
            <div className="glass-card p-5 rounded-xl flex flex-col justify-between gap-4">
              <div className="flex items-start justify-between">
                <div className="p-2.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <Database className="w-5 h-5" />
                </div>
                {getStatusBadge(health?.services?.postgres?.status)}
              </div>
              <div>
                <h4 className="font-semibold text-sm text-white">PostgreSQL 16</h4>
                <p className="text-xs text-slate-400">System of Record (SSOT)</p>
              </div>
              <div className="border-t border-slate-800/80 pt-3 flex items-center justify-between text-xs">
                <span className="text-slate-500">Latency</span>
                <span className="font-mono text-slate-300">
                  {health?.services?.postgres?.latency_ms !== undefined ? `${health.services.postgres.latency_ms} ms` : '—'}
                </span>
              </div>
            </div>

            {/* OpenSearch BM25 */}
            <div className="glass-card p-5 rounded-xl flex flex-col justify-between gap-4">
              <div className="flex items-start justify-between">
                <div className="p-2.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                  <Search className="w-5 h-5" />
                </div>
                {getStatusBadge(health?.services?.opensearch?.status)}
              </div>
              <div>
                <h4 className="font-semibold text-sm text-white">OpenSearch 2.x</h4>
                <p className="text-xs text-slate-400">Derived BM25 Lexical Index</p>
              </div>
              <div className="border-t border-slate-800/80 pt-3 flex items-center justify-between text-xs">
                <span className="text-slate-500">Latency</span>
                <span className="font-mono text-slate-300">
                  {health?.services?.opensearch?.latency_ms !== undefined ? `${health.services.opensearch.latency_ms} ms` : '—'}
                </span>
              </div>
            </div>

            {/* Qdrant Vectors */}
            <div className="glass-card p-5 rounded-xl flex flex-col justify-between gap-4">
              <div className="flex items-start justify-between">
                <div className="p-2.5 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20">
                  <Layers className="w-5 h-5" />
                </div>
                {getStatusBadge(health?.services?.qdrant?.status)}
              </div>
              <div>
                <h4 className="font-semibold text-sm text-white">Qdrant</h4>
                <p className="text-xs text-slate-400">Dense Vector Storage (HNSW)</p>
              </div>
              <div className="border-t border-slate-800/80 pt-3 flex items-center justify-between text-xs">
                <span className="text-slate-500">Latency</span>
                <span className="font-mono text-slate-300">
                  {health?.services?.qdrant?.latency_ms !== undefined ? `${health.services.qdrant.latency_ms} ms` : '—'}
                </span>
              </div>
            </div>

            {/* Redis Cache & Queue */}
            <div className="glass-card p-5 rounded-xl flex flex-col justify-between gap-4">
              <div className="flex items-start justify-between">
                <div className="p-2.5 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
                  <Activity className="w-5 h-5" />
                </div>
                {getStatusBadge(health?.services?.redis?.status)}
              </div>
              <div>
                <h4 className="font-semibold text-sm text-white">Redis 7</h4>
                <p className="text-xs text-slate-400">Cache & Rate Limits</p>
              </div>
              <div className="border-t border-slate-800/80 pt-3 flex items-center justify-between text-xs">
                <span className="text-slate-500">Latency</span>
                <span className="font-mono text-slate-300">
                  {health?.services?.redis?.latency_ms !== undefined ? `${health.services.redis.latency_ms} ms` : '—'}
                </span>
              </div>
            </div>

          </div>
        </div>

        {/* Phase Matrix Status */}
        <div className="glass-panel p-6 rounded-2xl border border-slate-800">
          <h3 className="font-semibold text-slate-200 mb-4 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-indigo-400" />
            Phase Matrix & Execution Progress
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/60 border border-emerald-500/30">
              <span className="font-medium text-emerald-300">Phase 0: Foundation & Infrastructure</span>
              <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px] font-semibold">ACTIVE</span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-900/30 border border-slate-800 text-slate-500">
              <span>Phase 1: Lexical Search Engine</span>
              <span>QUEUED</span>
            </div>
          </div>
        </div>

      </div>

      <footer className="border-t border-slate-800/80 py-4 px-6 text-center text-xs text-slate-500">
        Aegis Personal Search & Research Engine • Strict Local-First Architecture
      </footer>
    </main>
  );
}
