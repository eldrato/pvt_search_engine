'use client';

import { useState, useEffect, useRef } from 'react';
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
  Lock,
  Upload,
  FileText,
  FileCode,
  File,
  Plus,
  Trash2,
  X,
  Sliders,
  ChevronRight,
  Info,
  Clock,
  Sparkles,
  ExternalLink,
  Globe,
  Link2,
  Play,
  StopCircle,
  Eye,
  ZoomIn,
  ZoomOut,
  Download,
  ChevronLeft,
  BookOpen,
  Maximize2,
  Copy,
  Check,
  ToggleLeft,
  ToggleRight,
  PieChart,
  FolderCheck
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

interface ScoreBreakdown {
  base_bm25: number;
  title_boost: number;
  authority_boost: number;
  freshness_boost: number;
  phrase_boost: number;
  final_score: number;
  semantic_similarity?: number;
  lexical_rank?: number;
  semantic_rank?: number;
  rrf_score?: number;
  explanation: string[];
}

interface SearchHit {
  chunk_id: string;
  document_id: string;
  title: string;
  snippet: string;
  content: string;
  score: number;
  source_type: string;
  privacy_tier?: string;
  mime_type: string;
  anchor_label: string;
  chunk_index: number;
  location_meta: Record<string, any>;
  created_at?: string;
  score_breakdown?: ScoreBreakdown;
  semantic_score?: number;
  lexical_rank?: number;
  semantic_rank?: number;
  rrf_score?: number;
}

interface SearchResponse {
  query: string;
  total: number;
  latency_ms: number;
  engine: string;
  results: SearchHit[];
}

interface DocumentItem {
  id: string;
  title: string;
  source_type: string;
  privacy_tier?: string;
  file_path?: string;
  mime_type: string;
  file_size_bytes: number;
  content_hash: string;
  chunk_count: number;
  created_at?: string;
}

interface SourceConfigItem {
  source_type: string;
  name: string;
  description: string;
  icon: string;
  enabled: boolean;
  default_privacy_tier: string;
  allowed_privacy_tiers: string[];
  doc_count: number;
  chunk_count: number;
}

interface KnowledgeSummaryData {
  total_documents: number;
  total_chunks: number;
  privacy_tiers: Record<string, { count: number; percentage: number }>;
  sources: Record<string, { name: string; enabled: boolean; documents: number; chunks: number; default_privacy_tier: string }>;
  storage: Record<string, any>;
}

interface CrawlDomainItem {
  id: string;
  domain: string;
  description?: string;
  enabled: boolean;
  max_depth: number;
  rate_limit_delay: number;
  pages_crawled: number;
  last_crawled_at?: string;
  created_at?: string;
}

interface CrawlJobItem {
  id: string;
  seed_url: string;
  domain: string;
  status: string;
  max_depth: number;
  max_pages: number;
  pages_crawled: number;
  pages_failed: number;
  current_url?: string;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at?: string;
}

const API_BASE = 'http://localhost:8000/api/v1';

export default function AegisDashboard() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loadingHealth, setLoadingHealth] = useState<boolean>(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  // Search state
  const [query, setQuery] = useState<string>('');
  const [selectedSourceType, setSelectedSourceType] = useState<string>('all');
  const [searchMode, setSearchMode] = useState<'hybrid' | 'lexical' | 'semantic'>('hybrid');
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [hasSearched, setHasSearched] = useState<boolean>(false);
  const [selectedChunk, setSelectedChunk] = useState<SearchHit | null>(null);
  const [expandedBreakdowns, setExpandedBreakdowns] = useState<Record<string, boolean>>({});

  // Phase 5: Document Intelligence & Inline PDF Highlighter state
  const [docIntelTab, setDocIntelTab] = useState<'evidence' | 'pdf' | 'code' | 'signals'>('evidence');
  const [pdfPage, setPdfPage] = useState<number>(1);
  const [pdfTotalPages, setPdfTotalPages] = useState<number>(1);
  const [pdfZoom, setPdfZoom] = useState<number>(100);
  const [pdfHighlightQuery, setPdfHighlightQuery] = useState<boolean>(true);
  const [pdfHighlightChunk, setPdfHighlightChunk] = useState<boolean>(true);
  const [pdfViewMode, setPdfViewMode] = useState<'image' | 'embed'>('image');
  const [pdfPageLoading, setPdfPageLoading] = useState<boolean>(false);
  const [chunkContextData, setChunkContextData] = useState<any>(null);
  const [loadingContext, setLoadingContext] = useState<boolean>(false);
  const [copiedSnippet, setCopiedSnippet] = useState<boolean>(false);

  const fetchChunkContext = async (docId: string, chunkIndex: number) => {
    setLoadingContext(true);
    try {
      const res = await fetch(`${API_BASE}/documents/${docId}/location/${chunkIndex}`);
      if (res.ok) {
        const data = await res.json();
        setChunkContextData(data);
        if (data.total_pages) {
          setPdfTotalPages(data.total_pages);
        }
      }
    } catch (e) {
      console.error('Failed to load chunk context:', e);
    } finally {
      setLoadingContext(false);
    }
  };

  const handleOpenChunk = (hit: SearchHit, preferredTab?: 'evidence' | 'pdf' | 'code' | 'signals') => {
    setSelectedChunk(hit);
    const isPdf = hit.mime_type === 'application/pdf' || hit.location_meta?.filename?.endsWith('.pdf') || hit.location_meta?.pages?.length > 0;
    const isCode = hit.source_type === 'code' || hit.mime_type?.includes('code') || hit.location_meta?.language;
    const initialPage = hit.location_meta?.page_start || hit.location_meta?.pages?.[0] || 1;
    setPdfPage(initialPage);
    setPdfZoom(100);
    setPdfPageLoading(false);

    if (preferredTab) {
      setDocIntelTab(preferredTab);
    } else if (isPdf) {
      setDocIntelTab('pdf');
    } else if (isCode) {
      setDocIntelTab('code');
    } else {
      setDocIntelTab('evidence');
    }

    fetchChunkContext(hit.document_id, hit.chunk_index);
  };

  const handleCopySnippet = (text: string) => {
    if (navigator?.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedSnippet(true);
      setTimeout(() => setCopiedSnippet(false), 2000);
    }
  };

  const openDocumentInDrawer = async (docId: string, title: string, mimeType: string, sourceType: string) => {
    setIsLibraryOpen(false);
    try {
      const res = await fetch(`${API_BASE}/documents/${docId}`);
      if (res.ok) {
        const data = await res.json();
        const firstChunk = data.chunks?.[0] || {
          id: `${docId}_0`,
          chunk_index: 0,
          content: data.raw_content || 'No text extracted',
          location_meta: { pages: [1], page_start: 1 }
        };
        const mockHit: SearchHit = {
          chunk_id: firstChunk.id,
          document_id: docId,
          title: title,
          snippet: firstChunk.content?.slice(0, 150) || '',
          content: firstChunk.content || '',
          score: 1.0,
          source_type: sourceType,
          mime_type: mimeType,
          anchor_label: firstChunk.location_meta?.anchor_label || (firstChunk.location_meta?.pages?.length ? `Page ${firstChunk.location_meta.pages[0]}` : 'Chunk #1'),
          chunk_index: firstChunk.chunk_index || 0,
          location_meta: firstChunk.location_meta || {},
          created_at: data.created_at
        };
        handleOpenChunk(mockHit);
      }
    } catch (e) {
      console.error('Failed to open document:', e);
    }
  };

  const toggleBreakdown = (chunkId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedBreakdowns(prev => ({
      ...prev,
      [chunkId]: !prev[chunkId]
    }));
  };

  // Ingestion & Library state
  const [isIngestModalOpen, setIsIngestModalOpen] = useState<boolean>(false);
  const [activeIngestTab, setActiveIngestTab] = useState<'upload' | 'note'>('upload');
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loadingDocs, setLoadingDocs] = useState<boolean>(false);
  const [isLibraryOpen, setIsLibraryOpen] = useState<boolean>(false);

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [noteTitle, setNoteTitle] = useState<string>('');
  const [noteContent, setNoteContent] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Phase 6: Personal Knowledge Engine & Privacy Tier state
  const [sources, setSources] = useState<SourceConfigItem[]>([]);
  const [knowledgeSummary, setKnowledgeSummary] = useState<KnowledgeSummaryData | null>(null);
  const [isSourcesOpen, setIsSourcesOpen] = useState<boolean>(false);
  const [selectedPrivacyTier, setSelectedPrivacyTier] = useState<string>('all');
  const [includeSensitive, setIncludeSensitive] = useState<boolean>(true);
  const [ingestPrivacyTier, setIngestPrivacyTier] = useState<string>('private');

  const fetchHealth = async () => {
    setLoadingHealth(true);
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (res.ok) {
        const data: SystemHealth = await res.json();
        setHealth(data);
      } else {
        setHealth(null);
      }
    } catch (err) {
      setHealth(null);
    } finally {
      setLoadingHealth(false);
      setLastRefreshed(new Date());
    }
  };

  const fetchDocuments = async () => {
    setLoadingDocs(true);
    try {
      const res = await fetch(`${API_BASE}/documents?limit=50`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setLoadingDocs(false);
    }
  };

  const fetchSources = async () => {
    try {
      const res = await fetch(`${API_BASE}/sources`);
      if (res.ok) {
        const data = await res.json();
        setSources(data.sources || []);
      }
    } catch (err) {
      console.error('Failed to fetch sources:', err);
    }
  };

  const fetchKnowledgeSummary = async () => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/summary`);
      if (res.ok) {
        const data = await res.json();
        setKnowledgeSummary(data);
      }
    } catch (err) {
      console.error('Failed to fetch knowledge summary:', err);
    }
  };

  const handleToggleSource = async (sourceType: string, enabled: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/sources/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_type: sourceType, enabled }),
      });
      if (res.ok) {
        fetchSources();
        fetchKnowledgeSummary();
        if (query.trim()) handleSearch();
      }
    } catch (err) {
      console.error('Failed to toggle source:', err);
    }
  };

  const handleReclassify = async (docId: string, newTier: string) => {
    try {
      const res = await fetch(`${API_BASE}/documents/${docId}/classification`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ privacy_tier: newTier }),
      });
      if (res.ok) {
        fetchDocuments();
        fetchKnowledgeSummary();
        if (query.trim()) handleSearch();
      }
    } catch (err) {
      console.error('Failed to reclassify document:', err);
    }
  };

  // Crawler state
  const [isCrawlerOpen, setIsCrawlerOpen] = useState<boolean>(false);
  const [crawlDomains, setCrawlDomains] = useState<CrawlDomainItem[]>([]);
  const [crawlJobs, setCrawlJobs] = useState<CrawlJobItem[]>([]);
  const [newDomain, setNewDomain] = useState<string>('');
  const [newDomainDesc, setNewDomainDesc] = useState<string>('');
  const [crawlSeedUrl, setCrawlSeedUrl] = useState<string>('');
  const [crawlMaxDepth, setCrawlMaxDepth] = useState<number>(2);
  const [crawlMaxPages, setCrawlMaxPages] = useState<number>(20);
  const [isStartingCrawl, setIsStartingCrawl] = useState<boolean>(false);
  const [crawlStatusMsg, setCrawlStatusMsg] = useState<string | null>(null);
  const [crawlerActiveTab, setCrawlerActiveTab] = useState<'launch' | 'domains' | 'jobs'>('launch');

  const fetchCrawlerData = async () => {
    try {
      const [domRes, jobsRes] = await Promise.all([
        fetch(`${API_BASE}/crawler/domains`),
        fetch(`${API_BASE}/crawler/jobs?limit=20`)
      ]);
      if (domRes.ok) {
        const doms = await domRes.json();
        setCrawlDomains(doms);
      }
      if (jobsRes.ok) {
        const jobs = await jobsRes.json();
        setCrawlJobs(jobs);
      }
    } catch (err) {
      console.error('Failed to fetch crawler data:', err);
    }
  };

  const handleAddDomain = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDomain.trim()) return;
    setCrawlStatusMsg(null);
    try {
      const res = await fetch(`${API_BASE}/crawler/domains`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domain: newDomain.trim(),
          description: newDomainDesc.trim() || undefined,
          max_depth: 2,
          rate_limit_delay: 1.0,
        }),
      });
      if (res.ok) {
        setNewDomain('');
        setNewDomainDesc('');
        fetchCrawlerData();
        setCrawlStatusMsg('Domain allowlisted successfully!');
      } else {
        const err = await res.json();
        setCrawlStatusMsg(`Error: ${err.detail || 'Failed to add domain'}`);
      }
    } catch (err) {
      setCrawlStatusMsg(`Error: ${String(err)}`);
    }
  };

  const handleToggleDomain = async (domainId: string) => {
    try {
      const res = await fetch(`${API_BASE}/crawler/domains/${domainId}/toggle`, {
        method: 'PATCH',
      });
      if (res.ok) fetchCrawlerData();
    } catch (err) {
      console.error('Failed to toggle domain:', err);
    }
  };

  const handleDeleteDomain = async (domainId: string) => {
    try {
      const res = await fetch(`${API_BASE}/crawler/domains/${domainId}`, {
        method: 'DELETE',
      });
      if (res.ok) fetchCrawlerData();
    } catch (err) {
      console.error('Failed to delete domain:', err);
    }
  };

  const handleStartCrawl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!crawlSeedUrl.trim()) return;
    setIsStartingCrawl(true);
    setCrawlStatusMsg(null);
    try {
      const res = await fetch(`${API_BASE}/crawler/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seed_url: crawlSeedUrl.trim(),
          max_depth: crawlMaxDepth,
          max_pages: crawlMaxPages,
        }),
      });
      if (res.ok) {
        setCrawlSeedUrl('');
        setCrawlStatusMsg('Crawl job started in background!');
        setCrawlerActiveTab('jobs');
        fetchCrawlerData();
      } else {
        const err = await res.json();
        setCrawlStatusMsg(`Error: ${err.detail || 'Failed to start crawl'}`);
      }
    } catch (err) {
      setCrawlStatusMsg(`Error: ${String(err)}`);
    } finally {
      setIsStartingCrawl(false);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    try {
      const res = await fetch(`${API_BASE}/crawler/jobs/${jobId}/cancel`, {
        method: 'POST',
      });
      if (res.ok) fetchCrawlerData();
    } catch (err) {
      console.error('Failed to cancel job:', err);
    }
  };

  useEffect(() => {
    fetchHealth();
    fetchDocuments();
    fetchCrawlerData();
    fetchSources();
    fetchKnowledgeSummary();
    const interval = setInterval(() => {
      fetchHealth();
      fetchCrawlerData();
      fetchKnowledgeSummary();
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  // Poll more aggressively when a crawl job is running
  useEffect(() => {
    const hasRunningJob = crawlJobs.some(j => j.status === 'running' || j.status === 'queued');
    if (!hasRunningJob) return;

    const crawlInterval = setInterval(() => {
      fetchCrawlerData();
      fetchDocuments();
      fetchKnowledgeSummary();
    }, 2500);

    return () => clearInterval(crawlInterval);
  }, [crawlJobs]);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setSearchResponse(null);
      setHasSearched(false);
      return;
    }

    setIsSearching(true);
    setHasSearched(true);
    try {
      let url = `${API_BASE}/search?q=${encodeURIComponent(trimmed)}&limit=25&mode=${encodeURIComponent(searchMode)}`;
      if (selectedSourceType !== 'all') {
        url += `&source_type=${encodeURIComponent(selectedSourceType)}`;
      }
      if (selectedPrivacyTier !== 'all') {
        url += `&privacy_tier=${encodeURIComponent(selectedPrivacyTier)}`;
      }
      if (!includeSensitive) {
        url += `&include_sensitive=false`;
      }
      const res = await fetch(url);
      if (res.ok) {
        const data: SearchResponse = await res.json();
        setSearchResponse(data);
      } else {
        setSearchResponse(null);
      }
    } catch (err) {
      console.error('Search failed:', err);
      setSearchResponse(null);
    } finally {
      setIsSearching(false);
    }
  };

  // Debounced live search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (query.trim().length >= 2) {
        handleSearch();
      } else if (query.trim().length === 0 && hasSearched) {
        setSearchResponse(null);
        setHasSearched(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [query, selectedSourceType, searchMode, selectedPrivacyTier, includeSensitive]);

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;

    setIsUploading(true);
    setUploadStatus(null);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('source_type', 'upload');
      formData.append('privacy_tier', ingestPrivacyTier);

      const res = await fetch(`${API_BASE}/documents/upload`, {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        setUploadStatus(data.message || 'File ingested successfully!');
        setUploadFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
        fetchDocuments();
        fetchSources();
        fetchKnowledgeSummary();
      } else {
        const err = await res.json();
        setUploadStatus(`Error: ${err.detail || 'Upload failed'}`);
      }
    } catch (err) {
      setUploadStatus(`Error: ${String(err)}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleNoteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!noteTitle.trim() || !noteContent.trim()) return;

    setIsUploading(true);
    setUploadStatus(null);
    try {
      const res = await fetch(`${API_BASE}/documents/text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: noteTitle.trim(),
          content: noteContent.trim(),
          source_type: 'note',
          privacy_tier: ingestPrivacyTier,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setUploadStatus(data.message || 'Note saved and indexed successfully!');
        setNoteTitle('');
        setNoteContent('');
        fetchDocuments();
        fetchSources();
        fetchKnowledgeSummary();
      } else {
        const err = await res.json();
        setUploadStatus(`Error: ${err.detail || 'Failed to save note'}`);
      }
    } catch (err) {
      setUploadStatus(`Error: ${String(err)}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteDocument = async (docId: string, title: string) => {
    if (!confirm(`Are you sure you want to delete "${title}" and its indexed chunks?`)) return;
    try {
      const res = await fetch(`${API_BASE}/documents/${docId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        fetchDocuments();
        fetchSources();
        fetchKnowledgeSummary();
        if (searchResponse) {
          setSearchResponse({
            ...searchResponse,
            results: searchResponse.results.filter(r => r.document_id !== docId),
            total: Math.max(0, searchResponse.total - 1)
          });
        }
      }
    } catch (err) {
      console.error('Delete document failed:', err);
    }
  };

  const getSourceIcon = (mime: string, sourceType: string) => {
    if (sourceType === 'web') return <Globe className="w-4 h-4 text-cyan-400" />;
    if (mime.includes('pdf')) return <FileText className="w-4 h-4 text-rose-400" />;
    if (mime.includes('word') || mime.includes('docx')) return <FileText className="w-4 h-4 text-blue-400" />;
    if (mime.includes('markdown') || sourceType === 'note') return <FileText className="w-4 h-4 text-emerald-400" />;
    if (mime.includes('code') || mime.includes('javascript') || mime.includes('python')) return <FileCode className="w-4 h-4 text-amber-400" />;
    return <File className="w-4 h-4 text-slate-400" />;
  };

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case 'healthy':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3 h-3" /> Healthy
          </span>
        );
      case 'degraded':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertTriangle className="w-3 h-3" /> Degraded
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-500/10 text-slate-400 border border-slate-700">
            Offline
          </span>
        );
    }
  };

  return (
    <main className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      
      {/* Top Glass Header */}
      <header className="sticky top-0 z-40 glass-panel border-b border-slate-800/80 px-6 py-3.5 flex items-center justify-between shadow-xl">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 shadow-inner">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-base tracking-tight text-white">AEGIS</h1>
              <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 font-mono font-semibold">
                Phase 6 Active • Personal Knowledge Engine
              </span>
            </div>
            <p className="text-[11px] text-slate-400">Privacy-First Personal Search & Research Engine</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Phase 6: Sources & Privacy Engine Button */}
          <button
            onClick={() => {
              setIsSourcesOpen(true);
              fetchKnowledgeSummary();
              fetchSources();
            }}
            className="flex items-center gap-2 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg font-medium border border-slate-700/80 transition-all hover:border-indigo-500/40"
            id="sources-btn"
            title="Manage indexing sources and privacy tiers"
          >
            <Sliders className="w-3.5 h-3.5 text-indigo-400" />
            <span>Sources & Privacy</span>
            <span className="ml-1 px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 text-[10px] font-mono">
              {sources.length > 0 ? `${sources.filter(s => s.enabled).length}/${sources.length}` : '4/4'}
            </span>
          </button>

          {/* Web Crawler Button */}
          <button
            onClick={() => {
              setIsCrawlerOpen(true);
              setCrawlStatusMsg(null);
            }}
            className="flex items-center gap-2 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg font-medium border border-slate-700/80 transition-all hover:border-cyan-500/40"
            id="crawler-btn"
          >
            <Globe className="w-3.5 h-3.5 text-cyan-400" />
            <span>Web Crawler</span>
            {crawlJobs.some(j => j.status === 'running' || j.status === 'queued') && (
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
            )}
            <span className="ml-1 px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-300 text-[10px] font-mono">
              {crawlDomains.length}
            </span>
          </button>

          {/* Document Library Button */}
          <button
            onClick={() => setIsLibraryOpen(!isLibraryOpen)}
            className="flex items-center gap-2 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg font-medium border border-slate-700/80 transition-all"
            id="docs-library-btn"
          >
            <Database className="w-3.5 h-3.5 text-indigo-400" />
            <span>Documents</span>
            <span className="ml-1 px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 text-[10px] font-mono">
              {documents.length}
            </span>
          </button>

          {/* Ingest Button */}
          <button
            onClick={() => {
              setIsIngestModalOpen(true);
              setUploadStatus(null);
            }}
            className="flex items-center gap-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3.5 py-1.5 rounded-lg font-medium transition-all shadow-md shadow-indigo-600/20"
            id="open-ingest-btn"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Ingest Document</span>
          </button>

          {/* Health indicator badge */}
          <div className="hidden sm:flex items-center gap-1.5 text-[11px] text-slate-400 bg-slate-900/60 px-3 py-1 rounded-lg border border-slate-800">
            <Lock className="w-3 h-3 text-emerald-400" />
            <span>100% Local</span>
          </div>

          <button
            onClick={fetchHealth}
            disabled={loadingHealth}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-all"
            title="Refresh System Health"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingHealth ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="max-w-5xl mx-auto w-full px-6 py-8 flex-1 flex flex-col gap-6">

        {/* Search Hero Box */}
        <div className="glass-panel p-6 sm:p-8 rounded-2xl border border-indigo-500/20 shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none animate-glow" />

          <form onSubmit={handleSearch} className="flex flex-col gap-4 relative z-10">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-indigo-400" />
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                  Multi-Modal Hybrid Retrieval Engine (RRF Fusion)
                </span>
              </div>
              <div className="text-[11px] text-slate-400">
                {documents.length} document{documents.length === 1 ? '' : 's'} indexed in SSOT
              </div>
            </div>

            {/* Input bar */}
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-indigo-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search across PDF pages, docx, code lines, markdown, and notes..."
                className="w-full bg-slate-950/80 border border-indigo-500/30 rounded-xl py-3.5 pl-12 pr-24 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-500/30 transition-all shadow-inner"
                id="search-input"
                autoFocus
              />
              {query && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery('');
                    setSearchResponse(null);
                    setHasSearched(false);
                  }}
                  className="absolute right-14 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
              <button
                type="submit"
                disabled={isSearching}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition-all disabled:opacity-50"
              >
                {isSearching ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : 'Search'}
              </button>
            </div>

            {/* Search Mode & Source Filter Tags Row */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-1 text-xs">
              {/* Search Mode Selector */}
              <div className="flex items-center gap-1 bg-slate-950/90 p-1 rounded-lg border border-slate-800 shadow-inner">
                <span className="text-slate-400 text-[10px] font-bold uppercase tracking-wider px-2 flex items-center gap-1">
                  <Cpu className="w-3 h-3 text-indigo-400" /> Mode:
                </span>
                {[
                  { id: 'hybrid', label: '⚡ Hybrid (RRF)' },
                  { id: 'lexical', label: '🔍 Lexical (BM25)' },
                  { id: 'semantic', label: '🧠 Semantic (Vectors)' },
                ].map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => setSearchMode(m.id as any)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                      searchMode === m.id
                        ? 'bg-indigo-600 text-white font-semibold shadow-md shadow-indigo-600/30'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                    }`}
                  >
                    <span>{m.label}</span>
                  </button>
                ))}
              </div>

              {/* Source Filters */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-slate-500 flex items-center gap-1 text-[11px]">
                  <Sliders className="w-3 h-3" /> Sources:
                </span>
                {[
                  { id: 'all', label: 'All' },
                  { id: 'upload', label: 'Files' },
                  { id: 'note', label: 'Notes' },
                  { id: 'code', label: 'Code' },
                  { id: 'web', label: 'Web' }
                ].map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setSelectedSourceType(tab.id)}
                    className={`px-2 py-0.5 rounded-md text-xs font-medium transition-all ${
                      selectedSourceType === tab.id
                        ? 'bg-indigo-600/30 border border-indigo-500/50 text-indigo-300'
                        : 'bg-slate-900/50 border border-slate-800 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Phase 6: Privacy Tier Filters */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-slate-500 flex items-center gap-1 text-[11px]">
                  <Lock className="w-3 h-3 text-indigo-400" /> Tier:
                </span>
                {[
                  { id: 'all', label: 'All' },
                  { id: 'public', label: 'Public' },
                  { id: 'private', label: 'Private' },
                  { id: 'sensitive', label: 'Sensitive' }
                ].map((tier) => (
                  <button
                    key={tier.id}
                    type="button"
                    onClick={() => setSelectedPrivacyTier(tier.id)}
                    className={`px-2 py-0.5 rounded-md text-xs font-medium transition-all ${
                      selectedPrivacyTier === tier.id
                        ? tier.id === 'public'
                          ? 'bg-emerald-500/25 border border-emerald-500/40 text-emerald-300 font-semibold'
                          : tier.id === 'sensitive'
                          ? 'bg-rose-500/25 border border-rose-500/40 text-rose-300 font-semibold'
                          : 'bg-indigo-600/30 border border-indigo-500/50 text-indigo-300 font-semibold'
                        : 'bg-slate-900/50 border border-slate-800 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {tier.label}
                  </button>
                ))}

                {/* Sensitive Vault Toggle Guard */}
                <label className="flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-slate-200 cursor-pointer ml-1 select-none">
                  <input
                    type="checkbox"
                    checked={includeSensitive}
                    onChange={(e) => setIncludeSensitive(e.target.checked)}
                    className="rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0 focus:ring-offset-0 cursor-pointer"
                  />
                  <span className="flex items-center gap-1">
                    <AlertTriangle className={`w-3 h-3 ${includeSensitive ? 'text-amber-400' : 'text-slate-500'}`} />
                    <span>Vault Data</span>
                  </span>
                </label>
              </div>
            </div>
          </form>
        </div>

        {/* Search Results Statistics Banner */}
        {hasSearched && (
          <div className="flex items-center justify-between text-xs px-2 text-slate-400">
            <div className="flex items-center gap-2">
              <span className="text-slate-200 font-medium">
                {searchResponse?.total ?? 0} result{searchResponse?.total === 1 ? '' : 's'}
              </span>
              <span>for "{query}"</span>
              {searchResponse && (
                <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px] text-indigo-300 font-mono">
                  {searchResponse.latency_ms} ms • {searchResponse.engine}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Results List */}
        {searchResponse && searchResponse.results.length > 0 && (
          <div className="flex flex-col gap-3">
            {searchResponse.results.map((hit) => (
              <div
                key={hit.chunk_id}
                onClick={() => handleOpenChunk(hit)}
                className="glass-card p-5 rounded-xl cursor-pointer border border-slate-800/80 hover:border-indigo-500/50 flex flex-col gap-2.5 group"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    {getSourceIcon(hit.mime_type, hit.source_type)}
                    <div>
                      <h3 className="font-semibold text-sm text-slate-100 group-hover:text-indigo-300 transition-colors">
                        {hit.title}
                      </h3>
                      {hit.source_type === 'web' && hit.location_meta?.url && (
                        <a 
                          href={hit.location_meta.url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-[11px] text-cyan-400/90 hover:text-cyan-300 hover:underline flex items-center gap-1 font-mono mt-0.5"
                        >
                          <span>{hit.location_meta.domain || hit.location_meta.url}</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0 flex-wrap justify-end">
                    {/* Fusion / Match Type Badge */}
                    {hit.lexical_rank && hit.semantic_rank ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/20 border border-indigo-500/40 text-indigo-300 font-semibold">
                        <span>⚡ Hybrid RRF</span>
                        <span className="text-[9px] text-slate-400">BM25 #{hit.lexical_rank} · Vec #{hit.semantic_rank}</span>
                      </span>
                    ) : hit.semantic_rank ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/20 border border-purple-500/40 text-purple-300 font-semibold">
                        <span>🧠 Semantic</span>
                        <span className="text-[9px] text-slate-400">Vec #{hit.semantic_rank}</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 font-semibold">
                        <span>🔍 Lexical</span>
                      </span>
                    )}

                    {/* Phase 6: Privacy Tier Badge */}
                    {hit.privacy_tier && (
                      <span className={`inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded border capitalize ${
                        hit.privacy_tier === 'public'
                          ? 'bg-emerald-500/15 border-emerald-500/35 text-emerald-300'
                          : hit.privacy_tier === 'sensitive'
                          ? 'bg-rose-500/15 border-rose-500/35 text-rose-300 font-semibold'
                          : 'bg-indigo-500/15 border-indigo-500/35 text-indigo-300'
                      }`}>
                        {hit.privacy_tier === 'sensitive' ? (
                          <AlertTriangle className="w-2.5 h-2.5 text-rose-400" />
                        ) : hit.privacy_tier === 'public' ? (
                          <ShieldCheck className="w-2.5 h-2.5 text-emerald-400" />
                        ) : (
                          <Lock className="w-2.5 h-2.5 text-indigo-400" />
                        )}
                        <span>{hit.privacy_tier}</span>
                      </span>
                    )}

                    {/* Precision Anchor badge */}
                    <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20 text-indigo-300">
                      {hit.anchor_label}
                    </span>

                    {/* Document Intelligence Quick Action Pill */}
                    {(hit.mime_type === 'application/pdf' || hit.location_meta?.filename?.endsWith('.pdf') || hit.location_meta?.pages?.length > 0) ? (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleOpenChunk(hit, 'pdf');
                        }}
                        className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/35 text-emerald-300 hover:bg-emerald-500/25 transition-colors"
                        title="Open Inline PDF Highlighter"
                      >
                        <Eye className="w-3 h-3 text-emerald-400" />
                        <span>PDF Page {hit.location_meta?.page_start || hit.location_meta?.pages?.[0] || 1}</span>
                      </button>
                    ) : (hit.source_type === 'code' || hit.mime_type?.includes('code') || hit.location_meta?.language) ? (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleOpenChunk(hit, 'code');
                        }}
                        className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/35 text-cyan-300 hover:bg-cyan-500/25 transition-colors"
                        title="Open Code Line Inspector"
                      >
                        <FileCode className="w-3 h-3 text-cyan-400" />
                        <span>Lines {hit.location_meta?.line_start || 1}-{hit.location_meta?.line_end || 40}</span>
                      </button>
                    ) : null}

                    {/* Multi-Signal Composite Score with 'Why?' Toggle */}
                    <button
                      type="button"
                      onClick={(e) => toggleBreakdown(hit.chunk_id, e)}
                      className={`inline-flex items-center gap-1.5 text-[11px] font-mono px-2.5 py-0.5 rounded-full border transition-all ${
                        expandedBreakdowns[hit.chunk_id]
                          ? 'bg-indigo-600/30 border-indigo-400 text-indigo-200 shadow-sm shadow-indigo-500/20'
                          : 'bg-slate-800/90 hover:bg-slate-700/90 text-slate-300 border-slate-700 hover:border-indigo-500/40'
                      }`}
                      title="Inspect multi-signal ranking score and explainability signals"
                    >
                      <Sparkles className="w-3 h-3 text-indigo-400" />
                      <span className="font-semibold">{hit.score}</span>
                      <span className="text-[10px] text-indigo-300 font-sans ml-0.5 underline decoration-dotted">Why?</span>
                    </button>
                  </div>
                </div>

                {/* Highlighted Snippet */}
                <div 
                  className="text-xs text-slate-300 leading-relaxed font-sans line-clamp-3 bg-slate-950/40 p-3 rounded-lg border border-slate-900"
                  dangerouslySetInnerHTML={{ __html: hit.snippet }}
                />

                {/* Expandable Score Breakdown & Explainability Card */}
                {expandedBreakdowns[hit.chunk_id] && hit.score_breakdown && (
                  <div 
                    onClick={(e) => e.stopPropagation()}
                    className="bg-slate-950/90 rounded-xl p-4 border border-indigo-500/30 flex flex-col gap-3 my-1 shadow-inner"
                  >
                    <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                      <div className="flex items-center gap-2">
                        <div className="p-1 rounded bg-indigo-500/20 text-indigo-400">
                          <Sparkles className="w-3.5 h-3.5" />
                        </div>
                        <span className="text-xs font-semibold text-white tracking-wide">
                          Ranking Score Decomposition ("Why this result?")
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 text-[11px] font-mono text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                        <span>Composite Score:</span>
                        <span className="font-bold text-white">{hit.score_breakdown.final_score}</span>
                      </div>
                    </div>

                    {/* Signal Gauges Grid (6 Signals) */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 text-xs font-mono">
                      {/* 1. Base BM25 / Fused */}
                      <div className="p-2 rounded-lg bg-slate-900/90 border border-slate-800 flex flex-col gap-1">
                        <span className="text-[10px] text-slate-400 uppercase font-sans">
                          {hit.score_breakdown.rrf_score ? 'Fused RRF' : 'Base Lexical'}
                        </span>
                        <div className="flex items-baseline justify-between">
                          <span className="text-white font-bold">{hit.score_breakdown.base_bm25}</span>
                          <span className="text-[9px] text-slate-500">{hit.score_breakdown.rrf_score ? 'RRF' : 'BM25'}</span>
                        </div>
                        <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden mt-1">
                          <div className="bg-indigo-400 h-full rounded-full" style={{ width: `${Math.min(100, (hit.score_breakdown.base_bm25 / 10) * 100)}%` }} />
                        </div>
                      </div>

                      {/* 2. Semantic Similarity */}
                      <div className="p-2 rounded-lg bg-slate-900/90 border border-slate-800 flex flex-col gap-1">
                        <span className="text-[10px] text-slate-400 uppercase font-sans">Semantic Sim</span>
                        <div className="flex items-baseline justify-between">
                          <span className={`font-bold ${hit.score_breakdown.semantic_similarity !== undefined && hit.score_breakdown.semantic_similarity !== null ? 'text-purple-300' : 'text-slate-500'}`}>
                            {hit.score_breakdown.semantic_similarity !== undefined && hit.score_breakdown.semantic_similarity !== null
                              ? `${(hit.score_breakdown.semantic_similarity * 100).toFixed(1)}%`
                              : 'N/A'}
                          </span>
                          <span className="text-[9px] text-slate-500">Cosine</span>
                        </div>
                        <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden mt-1">
                          <div
                            className="bg-gradient-to-r from-indigo-500 to-purple-400 h-full rounded-full"
                            style={{ width: `${Math.min(100, Math.max(0, (hit.score_breakdown.semantic_similarity || 0) * 100))}%` }}
                          />
                        </div>
                      </div>

                      {/* 3. Title Boost */}
                      <div className="p-2 rounded-lg bg-slate-900/90 border border-slate-800 flex flex-col gap-1">
                        <span className="text-[10px] text-slate-400 uppercase font-sans">Title Match</span>
                        <div className="flex items-baseline justify-between">
                          <span className={`font-bold ${hit.score_breakdown.title_boost > 1.0 ? 'text-emerald-400' : 'text-slate-300'}`}>
                            {hit.score_breakdown.title_boost}x
                          </span>
                          <span className="text-[9px] text-slate-500">Prominence</span>
                        </div>
                        <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden mt-1">
                          <div className="bg-emerald-400 h-full rounded-full" style={{ width: `${Math.min(100, ((hit.score_breakdown.title_boost - 1.0) / 0.6) * 100)}%` }} />
                        </div>
                      </div>

                      {/* 4. Authority Boost */}
                      <div className="p-2 rounded-lg bg-slate-900/90 border border-slate-800 flex flex-col gap-1">
                        <span className="text-[10px] text-slate-400 uppercase font-sans">Authority</span>
                        <div className="flex items-baseline justify-between">
                          <span className="text-amber-400 font-bold">{hit.score_breakdown.authority_boost}x</span>
                          <span className="text-[9px] text-slate-500">{hit.source_type}</span>
                        </div>
                        <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden mt-1">
                          <div className="bg-amber-400 h-full rounded-full" style={{ width: `${Math.min(100, ((hit.score_breakdown.authority_boost - 1.0) / 0.5) * 100)}%` }} />
                        </div>
                      </div>

                      {/* 5. Freshness Factor */}
                      <div className="p-2 rounded-lg bg-slate-900/90 border border-slate-800 flex flex-col gap-1">
                        <span className="text-[10px] text-slate-400 uppercase font-sans">Freshness</span>
                        <div className="flex items-baseline justify-between">
                          <span className="text-cyan-400 font-bold">{hit.score_breakdown.freshness_boost}x</span>
                          <span className="text-[9px] text-slate-500">Decay</span>
                        </div>
                        <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden mt-1">
                          <div className="bg-cyan-400 h-full rounded-full" style={{ width: `${hit.score_breakdown.freshness_boost * 100}%` }} />
                        </div>
                      </div>

                      {/* 6. Phrase Proximity */}
                      <div className="p-2 rounded-lg bg-slate-900/90 border border-slate-800 flex flex-col gap-1">
                        <span className="text-[10px] text-slate-400 uppercase font-sans">Phrase Match</span>
                        <div className="flex items-baseline justify-between">
                          <span className={`font-bold ${hit.score_breakdown.phrase_boost > 1.0 ? 'text-purple-400' : 'text-slate-300'}`}>
                            {hit.score_breakdown.phrase_boost}x
                          </span>
                          <span className="text-[9px] text-slate-500">Proximity</span>
                        </div>
                        <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden mt-1">
                          <div className="bg-purple-400 h-full rounded-full" style={{ width: `${Math.min(100, ((hit.score_breakdown.phrase_boost - 1.0) / 0.25) * 100)}%` }} />
                        </div>
                      </div>
                    </div>

                    {/* Human Explanation Bullets */}
                    {hit.score_breakdown.explanation && hit.score_breakdown.explanation.length > 0 && (
                      <div className="flex flex-col gap-1.5 pt-1">
                        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                          Signal Analysis & Insights
                        </span>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[11px] text-slate-300">
                          {hit.score_breakdown.explanation.map((item, idx) => (
                            <div key={idx} className="flex items-start gap-1.5 bg-slate-900/50 px-2.5 py-1.5 rounded border border-slate-800/60">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                              <span>{item}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Formula Summary Footer */}
                    <div className="text-[10px] font-mono text-slate-500 bg-slate-900/60 px-3 py-1.5 rounded border border-slate-800/60 flex items-center justify-between">
                      <span>Formula: S = Base × M_title × M_auth × M_fresh × M_phrase</span>
                      <span className="text-indigo-400/90 font-semibold">100% Deterministic</span>
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1">
                  <span className="font-mono text-[10px] text-slate-600">
                    Chunk #{hit.chunk_index + 1}
                  </span>
                  <span className="text-indigo-400/80 group-hover:text-indigo-300 flex items-center gap-1 text-[11px]">
                    Inspect chunk & context <ChevronRight className="w-3 h-3" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty Search State */}
        {hasSearched && searchResponse && searchResponse.results.length === 0 && !isSearching && (
          <div className="glass-panel p-10 rounded-2xl text-center flex flex-col items-center gap-3">
            <Search className="w-8 h-8 text-slate-600" />
            <h3 className="font-semibold text-slate-300">No matching text found</h3>
            <p className="text-xs text-slate-500 max-w-sm">
              We couldn't find matches for "{query}". Try different terms or ingest documents to expand your personal index.
            </p>
            <button
              onClick={() => setIsIngestModalOpen(true)}
              className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" /> Ingest a new document or note
            </button>
          </div>
        )}

        {/* Default View (Before search) */}
        {!hasSearched && (
          <div className="flex flex-col gap-6">
            
            {/* Quick Actions & Overview */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
              <div 
                onClick={() => {
                  setIsIngestModalOpen(true);
                  setActiveIngestTab('upload');
                }}
                className="glass-card p-5 rounded-xl cursor-pointer flex flex-col gap-3 group"
              >
                <div className="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 w-fit group-hover:scale-105 transition-transform">
                  <Upload className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-semibold text-sm text-white">Upload Files</h4>
                  <p className="text-xs text-slate-400">Ingest PDF, DOCX, Markdown, or Code with precision line & page anchors.</p>
                </div>
              </div>

              <div 
                onClick={() => {
                  setIsIngestModalOpen(true);
                  setActiveIngestTab('note');
                }}
                className="glass-card p-5 rounded-xl cursor-pointer flex flex-col gap-3 group"
              >
                <div className="p-2.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 w-fit group-hover:scale-105 transition-transform">
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-semibold text-sm text-white">Write Quick Note</h4>
                  <p className="text-xs text-slate-400">Directly compose personal notes, meeting records, or research ideas.</p>
                </div>
              </div>

              <div 
                onClick={() => {
                  setIsCrawlerOpen(true);
                  setCrawlStatusMsg(null);
                }}
                className="glass-card p-5 rounded-xl cursor-pointer flex flex-col gap-3 group border border-slate-800 hover:border-cyan-500/40"
              >
                <div className="p-2.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 w-fit group-hover:scale-105 transition-transform">
                  <Globe className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-semibold text-sm text-white">Web Crawler</h4>
                  <p className="text-xs text-slate-400">Crawl and index allowlisted documentation, wikis, and technical blogs.</p>
                </div>
              </div>

              <div 
                onClick={() => setIsLibraryOpen(true)}
                className="glass-card p-5 rounded-xl cursor-pointer flex flex-col gap-3 group"
              >
                <div className="p-2.5 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20 w-fit group-hover:scale-105 transition-transform">
                  <Database className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-semibold text-sm text-white">SSOT Library</h4>
                  <p className="text-xs text-slate-400">View and manage all {documents.length} ingested documents and their chunk stats.</p>
                </div>
              </div>
            </div>

            {/* Storage Infrastructure Status Bar */}
            <div className="glass-panel p-5 rounded-xl border border-slate-800 flex flex-col gap-3">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-300 flex items-center gap-2">
                  <Server className="w-4 h-4 text-indigo-400" />
                  Storage Infrastructure & Derived Services
                </span>
                <span className="text-slate-500">
                  {lastRefreshed ? `Checked: ${lastRefreshed.toLocaleTimeString()}` : ''}
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 flex flex-col gap-1">
                  <span className="text-slate-400 text-[11px]">PostgreSQL (SSOT)</span>
                  {getStatusBadge(health?.services?.postgres?.status)}
                </div>
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 flex flex-col gap-1">
                  <span className="text-slate-400 text-[11px]">OpenSearch (BM25)</span>
                  {getStatusBadge(health?.services?.opensearch?.status)}
                </div>
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 flex flex-col gap-1">
                  <span className="text-slate-400 text-[11px]">Qdrant (Vectors)</span>
                  {getStatusBadge(health?.services?.qdrant?.status)}
                </div>
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 flex flex-col gap-1">
                  <span className="text-slate-400 text-[11px]">Redis (Queue)</span>
                  {getStatusBadge(health?.services?.redis?.status)}
                </div>
              </div>
            </div>

            {/* Roadmap Execution Matrix */}
            <div className="glass-panel p-5 rounded-xl border border-slate-800 flex flex-col gap-3">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                <span className="flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-indigo-400" />
                  Roadmap Phasing Matrix
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 text-xs">
                <div className="p-2.5 rounded-lg bg-slate-900/60 border border-emerald-500/30 flex items-center justify-between">
                  <span className="text-slate-300">Phase 0: Foundation</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">DONE</span>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900/60 border border-emerald-500/30 flex items-center justify-between">
                  <span className="text-slate-300">Phase 1: Lexical Search Core</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">DONE</span>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900/60 border border-emerald-500/30 flex items-center justify-between">
                  <span className="text-slate-300">Phase 2: Controlled Crawler</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">DONE</span>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900/60 border border-emerald-500/30 flex items-center justify-between">
                  <span className="text-slate-300">Phase 3: Multi-Signal Ranking</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">DONE</span>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900/60 border border-emerald-500/30 flex items-center justify-between">
                  <span className="text-slate-300">Phase 4: Semantic Vectors & Evaluation</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">DONE</span>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-900/60 border border-emerald-500/30 flex items-center justify-between">
                  <span className="text-slate-300">Phase 5: Document Intelligence</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">DONE</span>
                </div>
                <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/40 flex items-center justify-between">
                  <span className="text-white font-medium">Phase 6: Personal Knowledge Engine</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/30 text-emerald-300 font-mono font-semibold">DONE</span>
                </div>
              </div>
            </div>

          </div>
        )}

      </div>

      {/* Document Intelligence & Inline PDF Highlighter Workspace */}
      {selectedChunk && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/75 backdrop-blur-sm transition-opacity">
          <div className="w-full max-w-4xl bg-[#090d16] border-l border-slate-800/90 h-full flex flex-col shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="p-5 border-b border-slate-800/80 bg-slate-950/80 flex items-center justify-between gap-4 shrink-0">
              <div className="flex items-center gap-3 min-w-0">
                <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 shrink-0">
                  {getSourceIcon(selectedChunk.mime_type, selectedChunk.source_type)}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-bold text-base text-white truncate max-w-md">
                      {selectedChunk.title}
                    </h3>
                    <span className="px-2.5 py-0.5 rounded bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 font-mono text-[11px]">
                      {selectedChunk.anchor_label}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 text-[10px] font-mono">
                      Chunk #{selectedChunk.chunk_index + 1}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-400 mt-1">
                    <span className="font-mono text-[11px] text-slate-400">Score: <strong className="text-white">{selectedChunk.score}</strong></span>
                    <span>•</span>
                    <span className="text-[11px] text-slate-400">{selectedChunk.mime_type}</span>
                    {selectedChunk.location_meta?.filename && (
                      <>
                        <span>•</span>
                        <span className="font-mono text-[11px] text-indigo-300/80 truncate max-w-xs">{selectedChunk.location_meta.filename}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Header Action Buttons */}
              <div className="flex items-center gap-2 shrink-0">
                <a
                  href={`${API_BASE}/documents/${selectedChunk.document_id}/file`}
                  target="_blank"
                  rel="noreferrer"
                  className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium flex items-center gap-1.5 border border-slate-700 transition-colors"
                  title="Open or download original document file"
                >
                  <Download className="w-3.5 h-3.5 text-slate-300" />
                  <span className="hidden sm:inline">Raw File</span>
                </a>

                {(selectedChunk.mime_type === 'application/pdf' || selectedChunk.location_meta?.filename?.endsWith('.pdf') || selectedChunk.location_meta?.pages?.length > 0) && (
                  <a
                    href={`${API_BASE}/documents/${selectedChunk.document_id}/pdf/highlighted?highlight_chunk=${selectedChunk.chunk_index}${query ? `&highlight_query=${encodeURIComponent(query)}` : ''}`}
                    target="_blank"
                    rel="noreferrer"
                    className="px-2.5 py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 text-xs font-medium flex items-center gap-1.5 border border-emerald-500/30 transition-colors"
                    title="Download annotated PDF with standard highlight annotations"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="hidden sm:inline">Annotated PDF</span>
                  </a>
                )}

                <button
                  onClick={() => setSelectedChunk(null)}
                  className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-rose-500/20 text-slate-400 hover:text-rose-300 border border-slate-700 hover:border-rose-500/40 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Document Intelligence Tabs Bar */}
            <div className="flex border-b border-slate-800 bg-slate-950/60 px-5 gap-1 shrink-0 overflow-x-auto">
              <button
                onClick={() => setDocIntelTab('evidence')}
                className={`py-2.5 px-4 text-xs font-semibold flex items-center gap-2 border-b-2 transition-all whitespace-nowrap ${
                  docIntelTab === 'evidence'
                    ? 'border-indigo-500 text-indigo-300 bg-indigo-500/5'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <BookOpen className="w-3.5 h-3.5" />
                <span>Evidence & Context</span>
              </button>

              {(selectedChunk.mime_type === 'application/pdf' || selectedChunk.location_meta?.filename?.endsWith('.pdf') || selectedChunk.location_meta?.pages?.length > 0) && (
                <button
                  onClick={() => setDocIntelTab('pdf')}
                  className={`py-2.5 px-4 text-xs font-semibold flex items-center gap-2 border-b-2 transition-all whitespace-nowrap ${
                    docIntelTab === 'pdf'
                      ? 'border-emerald-500 text-emerald-300 bg-emerald-500/5'
                      : 'border-transparent text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Eye className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Inline PDF Highlighter</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 font-mono">
                    P.{selectedChunk.location_meta?.page_start || selectedChunk.location_meta?.pages?.[0] || 1}
                  </span>
                </button>
              )}

              {(selectedChunk.source_type === 'code' || selectedChunk.mime_type?.includes('code') || selectedChunk.location_meta?.language) && (
                <button
                  onClick={() => setDocIntelTab('code')}
                  className={`py-2.5 px-4 text-xs font-semibold flex items-center gap-2 border-b-2 transition-all whitespace-nowrap ${
                    docIntelTab === 'code'
                      ? 'border-cyan-500 text-cyan-300 bg-cyan-500/5'
                      : 'border-transparent text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <FileCode className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Code Inspector</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-300 font-mono">
                    L.{selectedChunk.location_meta?.line_start || 1}-{selectedChunk.location_meta?.line_end || 40}
                  </span>
                </button>
              )}

              <button
                onClick={() => setDocIntelTab('signals')}
                className={`py-2.5 px-4 text-xs font-semibold flex items-center gap-2 border-b-2 transition-all whitespace-nowrap ${
                  docIntelTab === 'signals'
                    ? 'border-purple-500 text-purple-300 bg-purple-500/5'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                <span>Ranking Signals ("Why?")</span>
                {selectedChunk.score_breakdown && (
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 font-mono">
                    {selectedChunk.score_breakdown.final_score}
                  </span>
                )}
              </button>
            </div>

            {/* Scrollable Tab Content */}
            <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-5">
              {/* TAB 1: Evidence & Context */}
              {docIntelTab === 'evidence' && (
                <div className="flex flex-col gap-5">
                  {/* Location Intelligence Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                    <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider">Precision Anchor</span>
                      <span className="text-white font-mono font-bold text-xs truncate mt-0.5">
                        {selectedChunk.anchor_label}
                      </span>
                    </div>

                    <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider">
                        {selectedChunk.location_meta?.pages?.length ? 'Page / Spread' : 'Lines'}
                      </span>
                      <span className="text-emerald-400 font-mono font-bold text-xs mt-0.5">
                        {selectedChunk.location_meta?.pages?.length 
                          ? `Page ${selectedChunk.location_meta.pages.join(', ')}`
                          : selectedChunk.location_meta?.line_start
                            ? `Lines ${selectedChunk.location_meta.line_start}-${selectedChunk.location_meta.line_end}`
                            : 'N/A'
                        }
                      </span>
                    </div>

                    <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider">Paragraph / Block</span>
                      <span className="text-cyan-400 font-mono font-bold text-xs mt-0.5">
                        {selectedChunk.location_meta?.paragraphs?.length 
                          ? `¶ ${selectedChunk.location_meta.paragraphs.join(', ')}`
                          : `Block #${selectedChunk.chunk_index + 1}`
                        }
                      </span>
                    </div>

                    <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-col">
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider">Estimated Tokens</span>
                      <span className="text-indigo-400 font-mono font-bold text-xs mt-0.5">
                        {selectedChunk.location_meta?.token_count || Math.round(selectedChunk.content.length / 4)} tokens
                      </span>
                    </div>
                  </div>

                  {/* Section Title banner if available */}
                  {selectedChunk.location_meta?.sections?.length > 0 && (
                    <div className="p-3 rounded-xl bg-indigo-950/30 border border-indigo-500/20 text-xs flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <BookOpen className="w-4 h-4 text-indigo-400" />
                        <span className="text-slate-400">Document Section:</span>
                        <strong className="text-indigo-200">{selectedChunk.location_meta.sections[0]}</strong>
                      </div>
                      <span className="text-[11px] text-slate-400 font-mono truncate max-w-xs">
                        {selectedChunk.location_meta.filename || selectedChunk.title}
                      </span>
                    </div>
                  )}

                  {/* Reading Context Flow: Previous, Matched, and Next Chunk */}
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                        <Layers className="w-3.5 h-3.5 text-indigo-400" />
                        Surrounding Reading Context
                      </span>
                      {loadingContext && (
                        <span className="text-[11px] text-indigo-300 flex items-center gap-1 font-mono">
                          <RefreshCw className="w-3 h-3 animate-spin" />
                          Loading Context...
                        </span>
                      )}
                    </div>

                    {/* Previous Chunk Preview if exists */}
                    {chunkContextData?.previous_chunk && (
                      <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/80 text-xs flex flex-col gap-1.5 opacity-80 hover:opacity-100 transition-opacity">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="text-slate-400 font-mono flex items-center gap-1">
                            <ChevronLeft className="w-3 h-3 text-slate-500" />
                            Previous: Chunk #{chunkContextData.previous_chunk.chunk_index + 1}
                          </span>
                          <span className="text-slate-400 font-mono">
                            {chunkContextData.previous_chunk.anchor_label}
                          </span>
                        </div>
                        <p className="text-slate-400 text-xs line-clamp-2 italic font-sans">
                          "{chunkContextData.previous_chunk.content}"
                        </p>
                      </div>
                    )}

                    {/* Current Matched Chunk (Highlight Centerpiece) */}
                    <div className="p-4 rounded-xl bg-slate-950 border-2 border-indigo-500/40 flex flex-col gap-3 shadow-lg shadow-indigo-500/5">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                        <div className="flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                          <span className="font-semibold text-xs text-white">
                            Current Matched Span ({selectedChunk.anchor_label})
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleCopySnippet(selectedChunk.content)}
                          className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[11px] text-slate-300 hover:text-white flex items-center gap-1 transition-colors"
                        >
                          {copiedSnippet ? (
                            <>
                              <Check className="w-3 h-3 text-emerald-400" />
                              <span className="text-emerald-400 font-mono">Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3 h-3 text-slate-400" />
                              <span className="font-mono">Copy Text</span>
                            </>
                          )}
                        </button>
                      </div>

                      <div className="text-xs text-slate-100 leading-relaxed font-mono whitespace-pre-wrap selection:bg-indigo-500 selection:text-white bg-slate-900/60 p-3.5 rounded-lg border border-slate-800/80">
                        {selectedChunk.content}
                      </div>

                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono pt-1">
                        <span>Characters: {selectedChunk.content.length}</span>
                        <span>SHA256 Hash: {selectedChunk.chunk_id.slice(0, 16)}...</span>
                      </div>
                    </div>

                    {/* Next Chunk Preview if exists */}
                    {chunkContextData?.next_chunk && (
                      <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/80 text-xs flex flex-col gap-1.5 opacity-80 hover:opacity-100 transition-opacity">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="text-slate-400 font-mono flex items-center gap-1">
                            Next: Chunk #{chunkContextData.next_chunk.chunk_index + 1}
                            <ChevronRight className="w-3 h-3 text-slate-500" />
                          </span>
                          <span className="text-slate-400 font-mono">
                            {chunkContextData.next_chunk.anchor_label}
                          </span>
                        </div>
                        <p className="text-slate-400 text-xs line-clamp-2 italic font-sans">
                          "{chunkContextData.next_chunk.content}"
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Anchor Metadata details */}
                  {selectedChunk.location_meta && Object.keys(selectedChunk.location_meta).length > 0 && (
                    <div className="flex flex-col gap-2 border-t border-slate-800 pt-3">
                      <span className="text-xs font-semibold text-slate-400">Structured Anchor Metadata</span>
                      <pre className="bg-slate-950/80 p-3.5 rounded-lg text-[11px] text-indigo-300 font-mono overflow-x-auto border border-slate-800">
                        {JSON.stringify(selectedChunk.location_meta, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: Inline PDF Highlighter */}
              {docIntelTab === 'pdf' && (
                <div className="flex flex-col gap-4">
                  {/* PDF Toolbar */}
                  <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
                    {/* Page Navigation */}
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={pdfPage <= 1}
                        onClick={() => setPdfPage(p => Math.max(1, p - 1))}
                        className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 transition-colors"
                        title="Previous page"
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </button>

                      <div className="flex items-center gap-1.5 font-mono text-xs">
                        <span>Page</span>
                        <input
                          type="number"
                          min={1}
                          max={pdfTotalPages || 999}
                          value={pdfPage}
                          onChange={(e) => {
                            const val = parseInt(e.target.value);
                            if (!isNaN(val) && val >= 1) setPdfPage(val);
                          }}
                          className="w-12 px-2 py-1 bg-slate-950 border border-slate-700 rounded text-center text-white font-mono focus:border-indigo-500 focus:outline-none"
                        />
                        <span className="text-slate-400">of {pdfTotalPages || 1}</span>
                      </div>

                      <button
                        type="button"
                        disabled={pdfPage >= (pdfTotalPages || 1)}
                        onClick={() => setPdfPage(p => p + 1)}
                        className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 transition-colors"
                        title="Next page"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>

                      {/* Jump to match button if on different page */}
                      {selectedChunk.location_meta?.page_start && selectedChunk.location_meta.page_start !== pdfPage && (
                        <button
                          type="button"
                          onClick={() => setPdfPage(selectedChunk.location_meta.page_start)}
                          className="ml-2 px-2 py-1 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30 text-[11px] font-mono transition-colors"
                        >
                          Jump to Match (P.{selectedChunk.location_meta.page_start})
                        </button>
                      )}
                    </div>

                    {/* Highlighting Toggles */}
                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-1.5 cursor-pointer text-slate-300 hover:text-white select-none">
                        <input
                          type="checkbox"
                          checked={pdfHighlightChunk}
                          onChange={(e) => setPdfHighlightChunk(e.target.checked)}
                          className="rounded bg-slate-950 border-slate-700 text-indigo-600 focus:ring-0"
                        />
                        <span className="text-[11px]">Highlight Chunk</span>
                      </label>

                      {query && (
                        <label className="flex items-center gap-1.5 cursor-pointer text-slate-300 hover:text-white select-none">
                          <input
                            type="checkbox"
                            checked={pdfHighlightQuery}
                            onChange={(e) => setPdfHighlightQuery(e.target.checked)}
                            className="rounded bg-slate-950 border-slate-700 text-yellow-500 focus:ring-0"
                          />
                          <span className="text-[11px]">Highlight Query</span>
                        </label>
                      )}
                    </div>

                    {/* Zoom & View Controls */}
                    <div className="flex items-center gap-2">
                      <div className="flex items-center rounded-lg bg-slate-950 border border-slate-800 p-0.5">
                        <button
                          type="button"
                          onClick={() => setPdfZoom(z => Math.max(60, z - 20))}
                          className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
                          title="Zoom out"
                        >
                          <ZoomOut className="w-3.5 h-3.5" />
                        </button>
                        <span className="px-1.5 text-[10px] font-mono text-slate-300">{pdfZoom}%</span>
                        <button
                          type="button"
                          onClick={() => setPdfZoom(z => Math.min(200, z + 20))}
                          className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
                          title="Zoom in"
                        >
                          <ZoomIn className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <div className="flex rounded-lg bg-slate-950 border border-slate-800 p-0.5 text-[11px]">
                        <button
                          type="button"
                          onClick={() => setPdfViewMode('image')}
                          className={`px-2 py-0.5 rounded font-medium transition-all ${
                            pdfViewMode === 'image' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                          }`}
                        >
                          Canvas
                        </button>
                        <button
                          type="button"
                          onClick={() => setPdfViewMode('embed')}
                          className={`px-2 py-0.5 rounded font-medium transition-all ${
                            pdfViewMode === 'embed' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                          }`}
                        >
                          Native Embed
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Viewer Canvas Area */}
                  {pdfViewMode === 'image' ? (
                    <div className="flex flex-col items-center bg-[#070a12] p-4 rounded-2xl border border-slate-800/80 min-h-[500px] overflow-auto relative">
                      {pdfPageLoading && (
                        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/50 backdrop-blur-sm rounded-2xl">
                          <div className="flex items-center gap-2 bg-slate-900 border border-indigo-500/40 px-4 py-2 rounded-xl text-xs text-indigo-300 font-mono">
                            <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                            Rendering High-Res Page {pdfPage}...
                          </div>
                        </div>
                      )}

                      <div 
                        style={{ width: `${pdfZoom}%`, maxWidth: '100%' }}
                        className="transition-all duration-150 flex flex-col items-center"
                      >
                        <img
                          key={`pdf_${selectedChunk.document_id}_${pdfPage}_${pdfHighlightChunk}_${pdfHighlightQuery}`}
                          src={`${API_BASE}/documents/${selectedChunk.document_id}/pdf/page/${pdfPage}?${
                            pdfHighlightChunk ? `highlight_chunk=${selectedChunk.chunk_index}&` : ''
                          }${
                            pdfHighlightQuery && query ? `highlight_query=${encodeURIComponent(query)}&` : ''
                          }t=${selectedChunk.document_id}_${pdfPage}`}
                          alt={`PDF Page ${pdfPage}`}
                          onLoad={() => setPdfPageLoading(false)}
                          className="w-full h-auto rounded-lg shadow-2xl border border-slate-700 bg-white"
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="w-full h-[650px] rounded-xl overflow-hidden border border-slate-800 bg-slate-950">
                      <iframe
                        src={`${API_BASE}/documents/${selectedChunk.document_id}/file#page=${pdfPage}`}
                        className="w-full h-full"
                        title={`PDF Document ${selectedChunk.title}`}
                      />
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: Code Inspector */}
              {docIntelTab === 'code' && (
                <div className="flex flex-col gap-4">
                  <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <FileCode className="w-4 h-4 text-cyan-400" />
                      <span className="font-mono text-cyan-300 font-semibold">
                        {selectedChunk.location_meta?.filename || selectedChunk.title}
                      </span>
                      {selectedChunk.location_meta?.language && (
                        <span className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-mono text-[10px]">
                          {selectedChunk.location_meta.language}
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleCopySnippet(selectedChunk.content)}
                      className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono flex items-center gap-1.5 transition-colors"
                    >
                      {copiedSnippet ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                          <span className="text-emerald-400">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5 text-slate-400" />
                          <span>Copy Snippet</span>
                        </>
                      )}
                    </button>
                  </div>

                  {/* Formatted Line-Numbered Code Block */}
                  <div className="bg-[#050811] rounded-xl border border-slate-800 overflow-hidden font-mono text-xs">
                    <div className="p-2 border-b border-slate-800/80 bg-slate-950/80 text-[11px] text-slate-400 flex items-center justify-between px-4">
                      <span>Source Lines {selectedChunk.location_meta?.line_start || 1} to {selectedChunk.location_meta?.line_end || 40}</span>
                      <span>UTF-8</span>
                    </div>

                    <div className="p-4 overflow-x-auto flex">
                      {/* Line Number Gutter */}
                      <div className="select-none text-slate-600 text-right pr-4 border-r border-slate-800/80 shrink-0 font-mono">
                        {selectedChunk.content.split('\n').map((_, idx) => {
                          const lineNum = (selectedChunk.location_meta?.line_start || 1) + idx;
                          return <div key={idx} className="leading-6">{lineNum}</div>;
                        })}
                      </div>

                      {/* Code Content */}
                      <div className="pl-4 text-slate-200 leading-6 whitespace-pre font-mono flex-1">
                        {selectedChunk.content.split('\n').map((line, idx) => (
                          <div key={idx} className="hover:bg-indigo-500/10 rounded px-1 transition-colors">
                            {line || ' '}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 4: Ranking Signals ("Why this result?") */}
              {docIntelTab === 'signals' && (
                <div className="flex flex-col gap-4">
                  {selectedChunk.score_breakdown ? (
                    <div className="bg-slate-950/70 p-5 rounded-2xl border border-indigo-500/20 flex flex-col gap-4 text-xs">
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                        <span className="font-semibold text-white text-sm flex items-center gap-1.5">
                          <Sparkles className="w-4 h-4 text-indigo-400" />
                          Ranking Signals & Explainability
                        </span>
                        <span className="text-xs font-mono text-indigo-300 bg-indigo-500/15 px-3 py-1 rounded-full border border-indigo-500/30">
                          Composite Score: <strong className="text-white">{selectedChunk.score_breakdown.final_score}</strong>
                        </span>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 font-mono text-xs">
                        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
                          <span className="text-[10px] text-slate-400 font-sans">Base BM25</span>
                          <span className="text-white font-bold text-sm mt-0.5">{selectedChunk.score_breakdown.base_bm25}</span>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
                          <span className="text-[10px] text-slate-400 font-sans">Title Boost</span>
                          <span className="text-emerald-400 font-bold text-sm mt-0.5">{selectedChunk.score_breakdown.title_boost}x</span>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
                          <span className="text-[10px] text-slate-400 font-sans">Authority Boost</span>
                          <span className="text-amber-400 font-bold text-sm mt-0.5">{selectedChunk.score_breakdown.authority_boost}x</span>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
                          <span className="text-[10px] text-slate-400 font-sans">Freshness Boost</span>
                          <span className="text-cyan-400 font-bold text-sm mt-0.5">{selectedChunk.score_breakdown.freshness_boost}x</span>
                        </div>
                        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
                          <span className="text-[10px] text-slate-400 font-sans">Phrase Match</span>
                          <span className="text-purple-400 font-bold text-sm mt-0.5">{selectedChunk.score_breakdown.phrase_boost}x</span>
                        </div>
                        {selectedChunk.score_breakdown.rrf_score && (
                          <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col">
                            <span className="text-[10px] text-slate-400 font-sans">RRF Fused Score</span>
                            <span className="text-indigo-400 font-bold text-sm mt-0.5">{selectedChunk.score_breakdown.rrf_score.toFixed(4)}</span>
                          </div>
                        )}
                      </div>

                      {selectedChunk.score_breakdown.explanation && (
                        <div className="flex flex-col gap-2 pt-2">
                          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                            Signal Explanations
                          </span>
                          <div className="flex flex-col gap-1.5 text-xs text-slate-300">
                            {selectedChunk.score_breakdown.explanation.map((item, idx) => (
                              <div key={idx} className="flex items-start gap-2 bg-slate-900/50 p-2.5 rounded-lg border border-slate-800/50">
                                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                                <span>{item}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="p-8 text-center text-slate-400 text-xs">
                      No explicit ranking score breakdown available for this chunk.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Ingest Document Modal */}
      {isIngestModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-xl rounded-2xl border border-indigo-500/30 p-6 flex flex-col gap-5 shadow-2xl relative">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Upload className="w-5 h-5 text-indigo-400" />
                <h3 className="font-bold text-base text-white">Ingest into Personal Intelligence</h3>
              </div>
              <button
                onClick={() => setIsIngestModalOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Ingest Tabs */}
            <div className="flex border-b border-slate-800">
              <button
                onClick={() => setActiveIngestTab('upload')}
                className={`flex-1 py-2 text-xs font-semibold text-center border-b-2 transition-all ${
                  activeIngestTab === 'upload'
                    ? 'border-indigo-500 text-indigo-300'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                Document Upload (PDF, Word, Code, MD)
              </button>
              <button
                onClick={() => setActiveIngestTab('note')}
                className={`flex-1 py-2 text-xs font-semibold text-center border-b-2 transition-all ${
                  activeIngestTab === 'note'
                    ? 'border-indigo-500 text-indigo-300'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                Direct Note / Text
              </button>
            </div>

            {/* Status Message */}
            {uploadStatus && (
              <div className={`p-3 rounded-lg text-xs ${
                uploadStatus.startsWith('Error')
                  ? 'bg-rose-500/10 border border-rose-500/30 text-rose-300'
                  : 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-300'
              }`}>
                {uploadStatus}
              </div>
            )}

            {/* Tab 1: Upload */}
            {activeIngestTab === 'upload' && (
              <form onSubmit={handleFileUpload} className="flex flex-col gap-4">
                <div 
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-700 hover:border-indigo-500/60 rounded-xl p-8 text-center cursor-pointer bg-slate-950/40 hover:bg-indigo-950/10 transition-all flex flex-col items-center gap-3"
                >
                  <Upload className="w-8 h-8 text-indigo-400" />
                  <div>
                    <p className="text-sm font-medium text-slate-200">
                      {uploadFile ? uploadFile.name : 'Click to select or drag and drop files'}
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      Supports PDF, DOCX, Markdown (.md), Source Code (.py, .ts, .js, .go), and Text files
                    </p>
                  </div>
                  {uploadFile && (
                    <span className="text-xs px-2.5 py-1 rounded bg-indigo-500/20 text-indigo-300 font-mono">
                      {(uploadFile.size / 1024).toFixed(1)} KB
                    </span>
                  )}
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    className="hidden"
                    accept=".pdf,.docx,.doc,.md,.txt,.py,.ts,.js,.tsx,.jsx,.html,.json,.yaml,.sql"
                  />
                </div>

                {/* Phase 6: Privacy Tier Classification Picker */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs text-slate-300 font-medium flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Lock className="w-3.5 h-3.5 text-indigo-400" />
                      Privacy Tier & Classification
                    </span>
                    <span className="text-[11px] text-slate-500">Tier controls indexing visibility</span>
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { id: 'public', label: 'Public', desc: 'Open domain / shared', color: 'emerald' },
                      { id: 'private', label: 'Private', desc: 'Personal workspace', color: 'indigo' },
                      { id: 'sensitive', label: 'Sensitive', desc: 'Vault & credentials', color: 'rose' }
                    ].map((tier) => (
                      <button
                        key={tier.id}
                        type="button"
                        onClick={() => setIngestPrivacyTier(tier.id)}
                        className={`p-2.5 rounded-xl border text-left flex flex-col gap-1 transition-all ${
                          ingestPrivacyTier === tier.id
                            ? tier.id === 'public'
                              ? 'bg-emerald-500/15 border-emerald-500/50 text-emerald-300 shadow-sm'
                              : tier.id === 'sensitive'
                              ? 'bg-rose-500/15 border-rose-500/50 text-rose-300 shadow-sm'
                              : 'bg-indigo-500/15 border-indigo-500/50 text-indigo-300 shadow-sm'
                            : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-xs text-white capitalize">{tier.label}</span>
                          {ingestPrivacyTier === tier.id && <Check className="w-3.5 h-3.5" />}
                        </div>
                        <span className="text-[10px] text-slate-400">{tier.desc}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setIsIngestModalOpen(false)}
                    className="px-4 py-2 rounded-lg text-xs bg-slate-800 text-slate-300 hover:bg-slate-700 font-medium"
                  >
                    Close
                  </button>
                  <button
                    type="submit"
                    disabled={!uploadFile || isUploading}
                    className="px-4 py-2 rounded-lg text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-all disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-indigo-600/20"
                  >
                    {isUploading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                    Ingest & Index
                  </button>
                </div>
              </form>
            )}

            {/* Tab 2: Note */}
            {activeIngestTab === 'note' && (
              <form onSubmit={handleNoteSubmit} className="flex flex-col gap-3">
                <div>
                  <label className="text-xs text-slate-400 font-medium block mb-1">Note Title</label>
                  <input
                    type="text"
                    value={noteTitle}
                    onChange={(e) => setNoteTitle(e.target.value)}
                    placeholder="e.g. Architecture Decisions, Meeting Summary, Ideas"
                    className="w-full bg-slate-950/80 border border-slate-700/80 rounded-lg p-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                    required
                  />
                </div>

                <div>
                  <label className="text-xs text-slate-400 font-medium block mb-1">Content</label>
                  <textarea
                    value={noteContent}
                    onChange={(e) => setNoteContent(e.target.value)}
                    rows={5}
                    placeholder="Type or paste markdown, notes, or research findings..."
                    className="w-full bg-slate-950/80 border border-slate-700/80 rounded-lg p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 font-mono"
                    required
                  />
                </div>

                {/* Phase 6: Privacy Tier Classification Picker for Notes */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs text-slate-300 font-medium flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Lock className="w-3.5 h-3.5 text-indigo-400" />
                      Privacy Tier & Classification
                    </span>
                    <span className="text-[11px] text-slate-500">Tier controls indexing visibility</span>
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { id: 'public', label: 'Public', desc: 'Open domain / shared', color: 'emerald' },
                      { id: 'private', label: 'Private', desc: 'Personal workspace', color: 'indigo' },
                      { id: 'sensitive', label: 'Sensitive', desc: 'Vault & credentials', color: 'rose' }
                    ].map((tier) => (
                      <button
                        key={tier.id}
                        type="button"
                        onClick={() => setIngestPrivacyTier(tier.id)}
                        className={`p-2.5 rounded-xl border text-left flex flex-col gap-1 transition-all ${
                          ingestPrivacyTier === tier.id
                            ? tier.id === 'public'
                              ? 'bg-emerald-500/15 border-emerald-500/50 text-emerald-300 shadow-sm'
                              : tier.id === 'sensitive'
                              ? 'bg-rose-500/15 border-rose-500/50 text-rose-300 shadow-sm'
                              : 'bg-indigo-500/15 border-indigo-500/50 text-indigo-300 shadow-sm'
                            : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-xs text-white capitalize">{tier.label}</span>
                          {ingestPrivacyTier === tier.id && <Check className="w-3.5 h-3.5" />}
                        </div>
                        <span className="text-[10px] text-slate-400">{tier.desc}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsIngestModalOpen(false)}
                    className="px-4 py-2 rounded-lg text-xs bg-slate-800 text-slate-300 hover:bg-slate-700 font-medium"
                  >
                    Close
                  </button>
                  <button
                    type="submit"
                    disabled={!noteTitle.trim() || !noteContent.trim() || isUploading}
                    className="px-4 py-2 rounded-lg text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-all disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-indigo-600/20"
                  >
                    {isUploading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                    Save Note
                  </button>
                </div>
              </form>
            )}

          </div>
        </div>
      )}

      {/* Document Library Modal */}
      {isLibraryOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-3xl max-h-[85vh] rounded-2xl border border-indigo-500/30 p-6 flex flex-col gap-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Database className="w-5 h-5 text-indigo-400" />
                <h3 className="font-bold text-base text-white">PostgreSQL SSOT Document Library</h3>
                <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-mono">
                  {documents.length} Items
                </span>
              </div>
              <button
                onClick={() => setIsLibraryOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="overflow-y-auto flex-1 flex flex-col gap-2.5 pr-1">
              {documents.length === 0 ? (
                <div className="text-center py-10 text-slate-500 text-xs">
                  No documents ingested yet. Click "Ingest Document" to start building your personal index.
                </div>
              ) : (
                documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/40 flex items-center justify-between gap-4 transition-all"
                  >
                    <div className="flex items-center gap-3 overflow-hidden">
                      {getSourceIcon(doc.mime_type, doc.source_type)}
                      <div className="overflow-hidden">
                        <h4 className="font-semibold text-xs text-white truncate max-w-md">
                          {doc.title}
                        </h4>
                        <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
                          <span className="capitalize">{doc.source_type}</span>
                          <span>•</span>
                          <span>{(doc.file_size_bytes / 1024).toFixed(1)} KB</span>
                          <span>•</span>
                          <span className="text-indigo-400 font-mono">{doc.chunk_count} chunks</span>
                          <span>•</span>
                          {/* Phase 6: Privacy Tier Reclassification Dropdown */}
                          <select
                            value={doc.privacy_tier || 'private'}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => handleReclassify(doc.id, e.target.value)}
                            className="bg-slate-950 border border-slate-700/80 rounded px-1.5 py-0.5 text-[10px] text-slate-300 focus:outline-none focus:border-indigo-500 font-mono cursor-pointer"
                            title="Reclassify Privacy Tier"
                          >
                            <option value="public">🟢 Public</option>
                            <option value="private">🔵 Private</option>
                            <option value="sensitive">🔴 Sensitive</option>
                          </select>
                          {doc.created_at && (
                            <>
                              <span>•</span>
                              <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        onClick={() => openDocumentInDrawer(doc.id, doc.title, doc.mime_type, doc.source_type)}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 text-xs border border-indigo-500/30 transition-colors"
                        title="Inspect in Document Intelligence Workspace"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>Inspect</span>
                      </button>
                      <a
                        href={`${API_BASE}/documents/${doc.id}/file`}
                        download={doc.title}
                        target="_blank"
                        rel="noreferrer"
                        className="p-2 text-slate-400 hover:text-cyan-300 rounded-lg hover:bg-cyan-500/10 transition-colors"
                        title="Download raw document file"
                      >
                        <Download className="w-4 h-4" />
                      </a>
                      <button
                        onClick={() => handleDeleteDocument(doc.id, doc.title)}
                        className="p-2 text-slate-500 hover:text-rose-400 rounded-lg hover:bg-rose-500/10 transition-colors"
                        title="Delete from SSOT and OpenSearch"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="flex justify-between items-center border-t border-slate-800 pt-3 text-xs">
              <span className="text-slate-500 text-[11px]">
                Deleting removes both PostgreSQL SSOT record and derived OpenSearch inverted indices.
              </span>
              <button
                onClick={() => setIsLibraryOpen(false)}
                className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Web Crawler Modal */}
      {isCrawlerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-3xl max-h-[88vh] rounded-2xl border border-cyan-500/30 p-6 flex flex-col gap-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                  <Globe className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-base text-white">Controlled Web Crawler</h3>
                  <p className="text-[11px] text-slate-400">Strictly bounded personal web indexing & URL frontier</p>
                </div>
              </div>
              <button
                onClick={() => setIsCrawlerOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Crawler Tabs */}
            <div className="flex border-b border-slate-800">
              <button
                onClick={() => setCrawlerActiveTab('launch')}
                className={`py-2 px-4 text-xs font-semibold border-b-2 transition-all ${
                  crawlerActiveTab === 'launch'
                    ? 'border-cyan-400 text-cyan-300'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                Launch Crawl
              </button>
              <button
                onClick={() => setCrawlerActiveTab('domains')}
                className={`py-2 px-4 text-xs font-semibold border-b-2 transition-all flex items-center gap-1.5 ${
                  crawlerActiveTab === 'domains'
                    ? 'border-cyan-400 text-cyan-300'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>Allowlisted Domains</span>
                <span className="px-1.5 py-0.2 rounded bg-slate-800 text-[10px] font-mono text-slate-300">
                  {crawlDomains.length}
                </span>
              </button>
              <button
                onClick={() => setCrawlerActiveTab('jobs')}
                className={`py-2 px-4 text-xs font-semibold border-b-2 transition-all flex items-center gap-1.5 ${
                  crawlerActiveTab === 'jobs'
                    ? 'border-cyan-400 text-cyan-300'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>Crawl Jobs</span>
                {crawlJobs.some(j => j.status === 'running') && (
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                )}
                <span className="px-1.5 py-0.2 rounded bg-slate-800 text-[10px] font-mono text-slate-300">
                  {crawlJobs.length}
                </span>
              </button>
            </div>

            {/* Status Message */}
            {crawlStatusMsg && (
              <div className={`p-3 rounded-lg text-xs ${
                crawlStatusMsg.startsWith('Error')
                  ? 'bg-rose-500/10 border border-rose-500/30 text-rose-300'
                  : 'bg-cyan-500/10 border border-cyan-500/30 text-cyan-300'
              }`}>
                {crawlStatusMsg}
              </div>
            )}

            {/* Tab 1: Launch Crawl */}
            {crawlerActiveTab === 'launch' && (
              <form onSubmit={handleStartCrawl} className="flex flex-col gap-4 overflow-y-auto">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs text-slate-300 font-medium">Seed URL to Crawl</label>
                  <input
                    type="url"
                    value={crawlSeedUrl}
                    onChange={(e) => setCrawlSeedUrl(e.target.value)}
                    placeholder="https://docs.python.org/3/tutorial/index.html"
                    className="w-full bg-slate-950/80 border border-slate-700/80 rounded-lg p-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono"
                    required
                  />
                  <span className="text-[11px] text-slate-500">
                    Aegis strictly respects robots.txt and will only crawl URLs matching your allowlist.
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs text-slate-300 font-medium">Max Crawl Depth</label>
                    <select
                      value={crawlMaxDepth}
                      onChange={(e) => setCrawlMaxDepth(Number(e.target.value))}
                      className="bg-slate-950/80 border border-slate-700/80 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-cyan-500"
                    >
                      <option value={1}>1 — Only seed and its direct links</option>
                      <option value={2}>2 — Follow links up to 2 hops (Recommended)</option>
                      <option value={3}>3 — Deep crawl (up to 3 hops)</option>
                    </select>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs text-slate-300 font-medium">Max Total Pages</label>
                    <select
                      value={crawlMaxPages}
                      onChange={(e) => setCrawlMaxPages(Number(e.target.value))}
                      className="bg-slate-950/80 border border-slate-700/80 rounded-lg p-2.5 text-xs text-white focus:outline-none focus:border-cyan-500"
                    >
                      <option value={5}>5 pages (Quick test)</option>
                      <option value={20}>20 pages (Balanced)</option>
                      <option value={50}>50 pages (Comprehensive)</option>
                      <option value={100}>100 pages (Large documentation)</option>
                    </select>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 flex flex-col gap-2">
                  <span className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider">
                    Allowlisted Domains Status
                  </span>
                  {crawlDomains.length === 0 ? (
                    <div className="text-[11px] text-amber-300/90 flex items-center gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      <span>No domains allowlisted yet. Starting a crawl will automatically add the seed domain.</span>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {crawlDomains.map(d => (
                        <span 
                          key={d.id} 
                          className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                            d.enabled 
                              ? 'bg-cyan-500/10 text-cyan-300 border-cyan-500/20' 
                              : 'bg-slate-800 text-slate-500 border-slate-700'
                          }`}
                        >
                          {d.domain}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsCrawlerOpen(false)}
                    className="px-4 py-2 rounded-lg text-xs bg-slate-800 text-slate-300 hover:bg-slate-700 font-medium"
                  >
                    Close
                  </button>
                  <button
                    type="submit"
                    disabled={!crawlSeedUrl.trim() || isStartingCrawl}
                    className="px-4 py-2 rounded-lg text-xs bg-cyan-600 hover:bg-cyan-500 text-white font-medium transition-all disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-cyan-600/20"
                  >
                    {isStartingCrawl ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                    Start Crawl Job
                  </button>
                </div>
              </form>
            )}

            {/* Tab 2: Allowlisted Domains */}
            {crawlerActiveTab === 'domains' && (
              <div className="flex flex-col gap-4 overflow-y-auto">
                <form onSubmit={handleAddDomain} className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 flex flex-col sm:flex-row gap-2">
                  <input
                    type="text"
                    value={newDomain}
                    onChange={(e) => setNewDomain(e.target.value)}
                    placeholder="e.g. news.ycombinator.com or *.python.org"
                    className="flex-1 bg-slate-950/80 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono"
                    required
                  />
                  <input
                    type="text"
                    value={newDomainDesc}
                    onChange={(e) => setNewDomainDesc(e.target.value)}
                    placeholder="Notes (optional)"
                    className="flex-1 bg-slate-950/80 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                  />
                  <button
                    type="submit"
                    className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold rounded-lg transition-all flex items-center justify-center gap-1 flex-shrink-0"
                  >
                    <Plus className="w-3.5 h-3.5" /> Add Domain
                  </button>
                </form>

                <div className="flex flex-col gap-2">
                  {crawlDomains.length === 0 ? (
                    <div className="text-center py-8 text-slate-500 text-xs">
                      No allowlisted domains configured. Add domains above to grant crawling access.
                    </div>
                  ) : (
                    crawlDomains.map(d => (
                      <div
                        key={d.id}
                        className="p-3 rounded-xl bg-slate-900/50 border border-slate-800 hover:border-cyan-500/30 flex items-center justify-between gap-3 transition-all"
                      >
                        <div className="flex items-center gap-2.5 overflow-hidden">
                          <Globe className={`w-4 h-4 flex-shrink-0 ${d.enabled ? 'text-cyan-400' : 'text-slate-600'}`} />
                          <div className="overflow-hidden">
                            <span className="font-mono text-xs font-medium text-white">
                              {d.domain}
                            </span>
                            {d.description && (
                              <p className="text-[11px] text-slate-400 truncate">{d.description}</p>
                            )}
                            <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
                              <span>{d.pages_crawled} pages indexed</span>
                              <span>•</span>
                              <span>Delay: {d.rate_limit_delay}s</span>
                              {d.last_crawled_at && (
                                <>
                                  <span>•</span>
                                  <span>Last: {new Date(d.last_crawled_at).toLocaleDateString()}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleToggleDomain(d.id)}
                            className={`px-2 py-1 rounded text-[11px] font-medium border transition-all ${
                              d.enabled
                                ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                                : 'bg-slate-800 text-slate-400 border-slate-700'
                            }`}
                          >
                            {d.enabled ? 'Enabled' : 'Disabled'}
                          </button>
                          <button
                            onClick={() => handleDeleteDomain(d.id)}
                            className="p-1.5 text-slate-500 hover:text-rose-400 rounded-lg hover:bg-rose-500/10 transition-colors"
                            title="Remove domain from allowlist"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* Tab 3: Crawl Jobs History */}
            {crawlerActiveTab === 'jobs' && (
              <div className="flex flex-col gap-3 overflow-y-auto max-h-[50vh]">
                {crawlJobs.length === 0 ? (
                  <div className="text-center py-10 text-slate-500 text-xs">
                    No crawl jobs executed yet. Launch your first crawl in the "Launch Crawl" tab!
                  </div>
                ) : (
                  crawlJobs.map(job => (
                    <div
                      key={job.id}
                      className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 flex flex-col gap-2"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 overflow-hidden">
                          <span className={`w-2 h-2 rounded-full ${
                            job.status === 'running' ? 'bg-cyan-400 animate-ping' :
                            job.status === 'completed' ? 'bg-emerald-400' :
                            job.status === 'failed' ? 'bg-rose-400' : 'bg-slate-500'
                          }`} />
                          <span className="font-mono text-xs text-white truncate max-w-sm">
                            {job.seed_url}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 flex-shrink-0">
                          <span className={`text-[10px] font-mono px-2 py-0.5 rounded border uppercase ${
                            job.status === 'running' ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' :
                            job.status === 'completed' ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' :
                            job.status === 'failed' ? 'bg-rose-500/20 text-rose-300 border-rose-500/30' :
                            'bg-slate-800 text-slate-400 border-slate-700'
                          }`}>
                            {job.status}
                          </span>

                          {(job.status === 'running' || job.status === 'queued') && (
                            <button
                              onClick={() => handleCancelJob(job.id)}
                              className="px-2 py-0.5 text-[11px] rounded bg-rose-500/10 text-rose-300 border border-rose-500/30 hover:bg-rose-500/20 flex items-center gap-1"
                            >
                              <StopCircle className="w-3 h-3" /> Cancel
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Progress bar */}
                      <div className="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden border border-slate-800">
                        <div 
                          className={`h-full transition-all duration-300 ${
                            job.status === 'completed' ? 'bg-emerald-500' :
                            job.status === 'failed' ? 'bg-rose-500' : 'bg-cyan-400'
                          }`}
                          style={{ width: `${Math.min(100, (job.pages_crawled / Math.max(1, job.max_pages)) * 100)}%` }}
                        />
                      </div>

                      <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
                        <span>
                          {job.pages_crawled} / {job.max_pages} pages crawled ({job.pages_failed} failed)
                        </span>
                        {job.current_url && (
                          <span className="truncate max-w-xs text-cyan-400/80">
                            Crawling: {job.current_url}
                          </span>
                        )}
                        {job.created_at && (
                          <span>{new Date(job.created_at).toLocaleTimeString()}</span>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            <div className="flex justify-between items-center border-t border-slate-800 pt-3 text-xs">
              <span className="text-slate-500 text-[11px]">
                Crawled pages are sanitized and saved to PostgreSQL SSOT and OpenSearch BM25 indices.
              </span>
              <button
                onClick={() => setIsCrawlerOpen(false)}
                className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Phase 6: Sources & Personal Knowledge Engine Modal */}
      {isSourcesOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-3xl max-h-[88vh] rounded-2xl border border-indigo-500/30 p-6 flex flex-col gap-5 shadow-2xl overflow-y-auto">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  <Sliders className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-base text-white">Personal Knowledge Engine</h3>
                  <p className="text-[11px] text-slate-400">Data source indexing toggles, storage metrics & privacy tiers</p>
                </div>
              </div>
              <button
                onClick={() => setIsSourcesOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Knowledge Overview Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col gap-1">
                <span className="text-[11px] text-slate-400 font-medium">Total Documents</span>
                <span className="text-xl font-bold text-white font-mono">
                  {knowledgeSummary?.total_documents ?? documents.length}
                </span>
                <span className="text-[10px] text-indigo-400">Indexed in SSOT & Engines</span>
              </div>
              <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col gap-1">
                <span className="text-[11px] text-slate-400 font-medium">Total Semantic Chunks</span>
                <span className="text-xl font-bold text-white font-mono">
                  {knowledgeSummary?.total_chunks ?? 0}
                </span>
                <span className="text-[10px] text-indigo-400">Vectorized in Qdrant & OpenSearch</span>
              </div>
              <div className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 flex flex-col gap-1">
                <span className="text-[11px] text-slate-400 font-medium">Active Data Sources</span>
                <span className="text-xl font-bold text-emerald-400 font-mono">
                  {sources.filter(s => s.enabled).length} / {sources.length || 4}
                </span>
                <span className="text-[10px] text-slate-500">Live search enabled</span>
              </div>
            </div>

            {/* Privacy Tier Distribution Bar */}
            {knowledgeSummary?.privacy_tiers && (
              <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 flex flex-col gap-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-300 flex items-center gap-1.5">
                    <PieChart className="w-4 h-4 text-indigo-400" />
                    Privacy Tier Breakdown
                  </span>
                  <span className="text-slate-500 text-[11px]">Dynamic classification breakdown</span>
                </div>

                <div className="w-full bg-slate-950 rounded-full h-3 overflow-hidden flex border border-slate-800">
                  <div
                    style={{ width: `${knowledgeSummary.privacy_tiers.public?.percentage || 0}%` }}
                    className="bg-emerald-500 transition-all duration-300"
                    title={`Public: ${knowledgeSummary.privacy_tiers.public?.count || 0}`}
                  />
                  <div
                    style={{ width: `${knowledgeSummary.privacy_tiers.private?.percentage || 0}%` }}
                    className="bg-indigo-500 transition-all duration-300"
                    title={`Private: ${knowledgeSummary.privacy_tiers.private?.count || 0}`}
                  />
                  <div
                    style={{ width: `${knowledgeSummary.privacy_tiers.sensitive?.percentage || 0}%` }}
                    className="bg-rose-500 transition-all duration-300"
                    title={`Sensitive: ${knowledgeSummary.privacy_tiers.sensitive?.count || 0}`}
                  />
                </div>

                <div className="flex items-center justify-between text-xs font-mono">
                  <div className="flex items-center gap-1.5 text-emerald-400">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                    <span>Public: {knowledgeSummary.privacy_tiers.public?.count || 0} ({knowledgeSummary.privacy_tiers.public?.percentage || 0}%)</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-indigo-400">
                    <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
                    <span>Private: {knowledgeSummary.privacy_tiers.private?.count || 0} ({knowledgeSummary.privacy_tiers.private?.percentage || 0}%)</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-rose-400">
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-500" />
                    <span>Sensitive: {knowledgeSummary.privacy_tiers.sensitive?.count || 0} ({knowledgeSummary.privacy_tiers.sensitive?.percentage || 0}%)</span>
                  </div>
                </div>
              </div>
            )}

            {/* Configured Data Sources List */}
            <div className="flex flex-col gap-3">
              <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                Configured Knowledge Ingestion Sources
              </span>

              <div className="flex flex-col gap-2.5">
                {sources.map((src) => (
                  <div
                    key={src.source_type}
                    className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/30 flex items-center justify-between gap-4 transition-all"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`p-2.5 rounded-xl border ${
                        src.enabled 
                          ? 'bg-indigo-500/10 border-indigo-500/30 text-indigo-400' 
                          : 'bg-slate-800 text-slate-500 border-slate-700'
                      }`}>
                        {src.source_type === 'upload' ? <File className="w-5 h-5" /> :
                         src.source_type === 'note' ? <FileText className="w-5 h-5" /> :
                         src.source_type === 'code' ? <FileCode className="w-5 h-5" /> :
                         <Globe className="w-5 h-5" />}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="font-semibold text-sm text-white">{src.name}</h4>
                          <span className={`text-[10px] px-2 py-0.5 rounded font-mono border capitalize ${
                            src.default_privacy_tier === 'public' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' :
                            src.default_privacy_tier === 'sensitive' ? 'bg-rose-500/10 border-rose-500/20 text-rose-300' :
                            'bg-indigo-500/10 border-indigo-500/20 text-indigo-300'
                          }`}>
                            Default: {src.default_privacy_tier}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 mt-0.5">{src.description}</p>
                        <div className="flex items-center gap-3 text-[11px] text-slate-500 font-mono mt-1">
                          <span>{src.doc_count} documents</span>
                          <span>•</span>
                          <span>{src.chunk_count} chunks indexed</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => handleToggleSource(src.source_type, !src.enabled)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 border transition-all ${
                          src.enabled
                            ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/25'
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700'
                        }`}
                      >
                        {src.enabled ? (
                          <>
                            <ToggleRight className="w-4 h-4 text-emerald-400" />
                            <span>Enabled</span>
                          </>
                        ) : (
                          <>
                            <ToggleLeft className="w-4 h-4 text-slate-500" />
                            <span>Disabled</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Privacy Architecture Notice */}
            <div className="p-3.5 rounded-xl bg-slate-900/40 border border-slate-800 text-[11px] text-slate-400 flex flex-col gap-1">
              <span className="font-semibold text-slate-300">Privacy & Exclusion Guarantee:</span>
              <span>Disabling a source excludes all its documents and vectors from hybrid search results instantly, while leaving PostgreSQL SSOT records intact. Sensitive documents are protected by vault guards.</span>
            </div>

            <div className="flex justify-end border-t border-slate-800 pt-3">
              <button
                onClick={() => setIsSourcesOpen(false)}
                className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-all"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-4 px-6 text-center text-xs text-slate-500 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <span>Aegis Personal Search & Research Engine</span>
        </div>
        <div className="text-[11px] font-mono text-indigo-400">
          Phase 6: Personal Knowledge Engine Active
        </div>
      </footer>
    </main>
  );
}
