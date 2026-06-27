import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import deltaLogo from './logo/delta.png'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000'
})

// Markdown Parser Helper Function
const parseMarkdown = (text) => {
  if (!text) return ''

  // Basic HTML escape to prevent XSS
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Headers
  html = html.replace(/^### (.*?)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.*?)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.*?)$/gm, '<h1>$1</h1>')

  // Bold (**text**)
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')

  // Inline Code (`code`)
  html = html.replace(/`(.*?)`/g, '<code>$1</code>')

  // Bullet Lists
  const lines = html.split('\n')
  let inList = false
  let inTable = false
  let tableRows = []

  const processedLines = lines.map(line => {
    const trimmed = line.trim()

    // Markdown Table Parser
    if (trimmed.startsWith('|')) {
      inTable = true
      const cells = trimmed.split('|').slice(1, -1).map(c => c.trim())
      // Check if it is a separator row (e.g. :--- or ---)
      if (cells.every(c => c.match(/^:?-+:?$/))) {
        return ''
      }
      tableRows.push(cells)
      return ''
    } else if (inTable) {
      inTable = false
      const tableHtml = renderHtmlTable(tableRows)
      tableRows = []
      return tableHtml + '\n' + line
    }

    // Unordered List Items
    if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
      const content = trimmed.substring(2)
      if (!inList) {
        inList = true
        return '<ul><li>' + content + '</li>'
      }
      return '<li>' + content + '</li>'
    } else {
      if (inList) {
        inList = false
        return '</ul>\n' + line
      }
    }
    return line
  })

  let result = processedLines.join('\n')
  if (inList) result += '</ul>'
  if (inTable && tableRows.length > 0) {
    result += renderHtmlTable(tableRows)
  }

  // Linebreaks
  result = result.replace(/\n\n/g, '<br /><br />')
  result = result.replace(/\n/g, '<br />')

  return result
}

const renderHtmlTable = (rows) => {
  if (rows.length === 0) return ''
  let html = '<div class="table-container" style="margin: 0.75rem 0;"><table style="width:100%; border-collapse:collapse; font-size:0.8rem;">'

  // Header Row
  html += '<thead><tr style="border-bottom: 2px solid rgba(255,255,255,0.1);">'
  rows[0].forEach(cell => {
    html += `<th style="padding: 6px; text-align: left; color: #9ca3af; font-weight:700;">${cell}</th>`
  })
  html += '</tr></thead><tbody>'

  // Data Rows
  for (let i = 1; i < rows.length; i++) {
    html += '<tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">'
    rows[i].forEach(cell => {
      let style = 'padding: 6px; text-align: left;'
      if (cell.includes('🟢') || (cell.includes('₹') && !cell.includes('-₹') && parseFloat(cell.replace(/[^0-9.-]/g, '')) > 0)) {
        style += ' color: #10b981; font-weight: 600;'
      } else if (cell.includes('🔴') || cell.includes('₹') && cell.includes('-') || (cell.includes('₹') && parseFloat(cell.replace(/[^0-9.-]/g, '')) < 0)) {
        style += ' color: #ef4444; font-weight: 600;'
      }
      html += `<td style="${style}">${cell}</td>`
    })
    html += '</tr>'
  }

  html += '</tbody></table></div>'
  return html
}

// --- localStorage helpers ---
const STORAGE_KEYS = {
  MESSAGES: 'aegis_chat_messages',
  ACTIVE_TAB: 'aegis_active_tab',
}

const loadMessages = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.MESSAGES)
    if (raw) {
      const parsed = JSON.parse(raw)
      // Restore Date objects from ISO strings
      return parsed.map(m => ({ ...m, timestamp: new Date(m.timestamp) }))
    }
  } catch (e) {
    console.warn('Failed to load chat history from localStorage:', e)
  }
  return [
    {
      sender: 'assistant',
      text: "**Welcome to Delta Options!**\n\nI am your Options Execution & Auto-Trading Terminal. I'm connected to the backend. Please provide your **6-digit Google Authenticator TOTP** to establish a secure, live trading session with Kotak Neo.",
      timestamp: new Date()
    }
  ]
}

const saveMessages = (msgs) => {
  try {
    // Keep last 200 messages to avoid bloating localStorage
    const toSave = msgs.slice(-200)
    localStorage.setItem(STORAGE_KEYS.MESSAGES, JSON.stringify(toSave))
  } catch (e) {
    console.warn('Failed to save chat history to localStorage:', e)
  }
}

function App() {
  // Initial loading flag — prevents login form flash while we check backend auth
  const [initialLoading, setInitialLoading] = useState(true)

  // Connection states
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isOnline, setIsOnline] = useState(false)
  const [totp, setTotp] = useState('')
  const [isLoggingIn, setIsLoggingIn] = useState(false)

  // Autotrade states
  const [autotradeEnabled, setAutotradeEnabled] = useState(false)
  const [isAutotradeToggling, setIsAutotradeToggling] = useState(false)
  const [rateLimited, setRateLimited] = useState(false)
  const [cooldownRemaining, setCooldownRemaining] = useState(0)

  // Market & Portfolio Data states
  const [marketData, setMarketData] = useState({
    nifty: { ltp: '0.00', open: '0.00', high: '0.00', low: '0.00', close: '0.00' },
    banknifty: { ltp: '0.00', open: '0.00', high: '0.00', low: '0.00', close: '0.00' },
    india_vix: { vix: '0.00' }
  })
  const [niftyFlash, setNiftyFlash] = useState('') // 'flash-up' or 'flash-down'
  const [bankniftyFlash, setBankniftyFlash] = useState('')

  const [positions, setPositions] = useState([])
  const [holdings, setHoldings] = useState([])
  const [margin, setMargin] = useState('0.00')

  // History & Analytics states
  const [trades, setTrades] = useState([])
  const [analytics, setAnalytics] = useState(null)

  // UI Active Tab — persisted to localStorage
  const [activeTab, setActiveTab] = useState(() => {
    return localStorage.getItem(STORAGE_KEYS.ACTIVE_TAB) || 'positions'
  })

  // Chat Assistant states — persisted to localStorage
  const [messages, setMessages] = useState(loadMessages)
  const [chatInput, setChatInput] = useState('')
  const [isSending, setIsSending] = useState(false)

  // Manual Order Form states
  const [manualSymbol, setManualSymbol] = useState('NIFTY')
  const [manualOptionType, setManualOptionType] = useState('CALL')
  const [manualStrike, setManualStrike] = useState('')
  const [manualExpiry, setManualExpiry] = useState('2026-07-02')
  const [manualQty, setManualQty] = useState('50')
  const [manualSL, setManualSL] = useState('')
  const [manualTarget, setManualTarget] = useState('')
  const [isPlacingOrder, setIsPlacingOrder] = useState(false)

  // Beast Category 3 Premium States
  const [settings, setSettings] = useState({
    max_daily_loss: 1000,
    risk_percent: 2.0,
    default_quantity: 50,
    min_risk_reward: 2.0,
    max_open_trades: 1,
    paper_trading: true
  })
  const [isSavingSettings, setIsSavingSettings] = useState(false)
  const [lastDecision, setLastDecision] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [optionChainData, setOptionChainData] = useState([])
  const [optionChainSpot, setOptionChainSpot] = useState(0)
  const [optionChainSymbol, setOptionChainSymbol] = useState('NIFTY')
  const [isOptionChainLoading, setIsOptionChainLoading] = useState(false)

  const messagesEndRef = useRef(null)

  // Scroll to bottom of chat
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    if (!initialLoading) {
      const timer = setTimeout(scrollToBottom, 100)
      return () => clearTimeout(timer)
    }
  }, [messages, initialLoading])

  // Check connection status & retrieve portfolio summary
  const checkConnection = async () => {
    try {
      const res = await api.get('/portfolio')
      if (res.data.success) {
        setIsAuthenticated(true)
        setIsOnline(true)

        // Kotak Neo returns positions/holdings in nested 'data' wrappers
        const rawPos = res.data.data?.positions?.data || res.data.data?.positions || []
        const rawHolds = res.data.data?.holdings?.data || res.data.data?.holdings || []
        const limits = res.data.data?.limits || {}

        setPositions(Array.isArray(rawPos) ? rawPos : [])
        setHoldings(Array.isArray(rawHolds) ? rawHolds : [])

        const netLimit = limits.Net || limits.data?.Net || '0.00'
        setMargin(parseFloat(netLimit).toLocaleString('en-IN', { minimumFractionDigits: 2 }))
      } else {
        setIsAuthenticated(false)
        setIsOnline(true)
      }
    } catch (err) {
      console.error('Connection check failed:', err)
      setIsOnline(false)
    }
  }

  // Fetch Market Indices
  const fetchMarketData = async () => {
    try {
      const res = await api.get('/market')
      if (res.data.success && res.data.data) {
        const newData = res.data.data

        // Calculate visual flashes on price ticks
        const prevNifty = parseFloat(marketData.nifty?.ltp || 0)
        const newNifty = parseFloat(newData.nifty?.ltp || 0)
        if (prevNifty > 0 && newNifty !== prevNifty) {
          setNiftyFlash(newNifty > prevNifty ? 'flash-up' : 'flash-down')
          setTimeout(() => setNiftyFlash(''), 1000)
        }

        const prevBanknifty = parseFloat(marketData.banknifty?.ltp || 0)
        const newBanknifty = parseFloat(newData.banknifty?.ltp || 0)
        if (prevBanknifty > 0 && newBanknifty !== prevBanknifty) {
          setBankniftyFlash(newBanknifty > prevBanknifty ? 'flash-up' : 'flash-down')
          setTimeout(() => setBankniftyFlash(''), 1000)
        }

        setMarketData(newData)
      }
    } catch (err) {
      console.error('Market data fetch failed:', err)
    }
  }

  // Fetch Autotrade status
  const fetchAutotradeStatus = async () => {
    try {
      const res = await api.get('/autotrade/status')
      if (res.data.success) {
        setAutotradeEnabled(res.data.data?.enabled || false)
        setRateLimited(res.data.data?.rate_limited || false)
        setCooldownRemaining(res.data.data?.cooldown_remaining || 0)
      }
    } catch (err) {
      console.error('Autotrade status fetch failed:', err)
    }
  }

  // Fetch Trade History Log
  const fetchTradeHistory = async () => {
    try {
      const res = await api.get('/trade/history')
      if (res.data.success && Array.isArray(res.data.data)) {
        setTrades(res.data.data)
      }
    } catch (err) {
      console.error('Trade history fetch failed:', err)
    }
  }

  // Fetch performance metrics
  const fetchAnalytics = async () => {
    try {
      const res = await api.get('/analytics')
      if (res.data.success) {
        setAnalytics(res.data.data)
      }
    } catch (err) {
      console.error('Analytics fetch failed:', err)
    }
  }

  // Beast Category 3 Settings & Decision API Calls
  const fetchSettings = async () => {
    try {
      const res = await api.get('/autotrade/settings')
      if (res.data.success && res.data.data) {
        setSettings(res.data.data)
      }
    } catch (err) {
      console.error('Settings fetch failed:', err)
    }
  }

  const saveSettings = async (updatedSettings) => {
    setIsSavingSettings(true)
    try {
      const res = await api.post('/autotrade/settings', updatedSettings)
      if (res.data.success) {
        setSettings(res.data.data)
        alert('Settings updated successfully!')
        // Refresh margin and details to show paper vs live values
        refreshAll()
      } else {
        alert('Failed to save settings: ' + res.data.message)
      }
    } catch (err) {
      alert('Failed to save settings: server communication error')
    } finally {
      setIsSavingSettings(false)
    }
  }

  const fetchLastDecision = async () => {
    try {
      const res = await api.get('/autotrade/last-decision')
      if (res.data.success && res.data.data) {
        setLastDecision(res.data.data)
      }
    } catch (err) {
      console.error('Failed to fetch last decision details:', err)
    }
  }

  // Fetch Kotak Neo Options Chain
  const fetchOptionChain = async (symbol) => {
    setIsOptionChainLoading(true)
    try {
      const res = await api.get(`/market/optionchain?symbol=${symbol || optionChainSymbol}`)
      if (res.data.success && res.data.data) {
        setOptionChainData(res.data.data.data || [])
        setOptionChainSpot(res.data.data.spot_price || 0)
        setOptionChainSymbol(res.data.data.symbol || symbol || optionChainSymbol)
      }
    } catch (err) {
      console.error('Failed to fetch option chain:', err)
    } finally {
      setIsOptionChainLoading(false)
    }
  }

  // Toggle autotrade background loop
  const toggleAutotrade = async (targetState) => {
    setIsAutotradeToggling(true)
    try {
      const endpoint = targetState ? '/autotrade/enable' : '/autotrade/disable'
      const res = await api.post(endpoint)
      if (res.data.success) {
        setAutotradeEnabled(targetState)
        // Add status log to AI chat
        setMessages(prev => [
          ...prev,
          {
            sender: 'assistant',
            text: `**AutoTrade Notification**\n\nBackground scanning and auto-trading has been **${targetState ? 'ENABLED' : 'DISABLED'}**.`,
            timestamp: new Date()
          }
        ])
      } else {
        alert(res.data.message || 'Action failed')
      }
    } catch (err) {
      alert('Failed to update autotrade state')
    } finally {
      setIsAutotradeToggling(false)
    }
  }

  // Manual TOTP Login
  const handleLogin = async (e) => {
    if (e) e.preventDefault()
    if (!totp || totp.trim().length !== 6) {
      return alert('Please enter a valid 6-digit TOTP code')
    }
    setIsLoggingIn(true)
    try {
      const res = await api.post('/login', { totp })
      if (res.data.success) {
        setTotp('')
        await refreshAll()
        setMessages(prev => [
          ...prev,
          {
            sender: 'assistant',
            text: '**Connection established successfully!**\n\nYour Kotak Neo session is active. Live data stream running, and positions are synchronized.',
            timestamp: new Date()
          }
        ])
      } else {
        alert('Authentication failed: ' + res.data.message)
      }
    } catch (err) {
      alert('Authentication error: Unable to contact login server')
    } finally {
      setIsLoggingIn(false)
    }
  }

  // Send message to assistant
  const handleSendMessage = async (textToSend) => {
    const msgText = textToSend || chatInput
    if (!msgText.trim()) return

    // Add user message locally
    setMessages(prev => [...prev, { sender: 'user', text: msgText, timestamp: new Date() }])
    if (!textToSend) setChatInput('')

    setIsSending(true)
    try {
      const res = await api.post('/chat', { message: msgText })
      if (res.data.success) {
        setMessages(prev => [...prev, {
          sender: 'assistant',
          text: res.data.data.reply,
          timestamp: new Date()
        }])

        // If the reply includes login success indicators, re-establish connection
        if (res.data.data.reply.includes('Login Successful') || res.data.data.reply.includes('authenticated')) {
          refreshAll()
        }

        // Refresh logs and positions in case trades were triggered or exited
        checkConnection()
        fetchTradeHistory()
        fetchAnalytics()
      } else {
        setMessages(prev => [...prev, {
          sender: 'assistant',
          text: 'Sorry, there was an issue processing that command.',
          timestamp: new Date()
        }])
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        sender: 'assistant',
        text: 'Network error: Unable to reach the AI engine.',
        timestamp: new Date()
      }])
    } finally {
      setIsSending(false)
    }
  }

  // Place Manual Order via form
  const handlePlaceManualOrder = async (e) => {
    e.preventDefault()
    if (!manualStrike || parseFloat(manualStrike) <= 0) return alert('Enter strike price')
    if (!manualExpiry) return alert('Enter expiry date (YYYY-MM-DD)')
    if (!manualQty || parseInt(manualQty) <= 0) return alert('Enter quantity')

    setIsPlacingOrder(true)
    try {
      const payload = {
        symbol: manualSymbol,
        strike: parseFloat(manualStrike),
        expiry: manualExpiry,
        option_type: manualOptionType === 'CALL' ? 'CALL' : 'PUT',
        quantity: parseInt(manualQty),
        stoploss: manualSL ? parseFloat(manualSL) : null,
        target: manualTarget ? parseFloat(manualTarget) : null,
        reason: 'Manual buy order via Terminal form'
      }

      const res = await api.post('/trade/buy', payload)
      if (res.data.success) {
        alert('Order dispatched successfully!')
        setActiveTab('positions')
        refreshAll()
        // Reset form
        setManualStrike('')
        setManualSL('')
        setManualTarget('')
      } else {
        alert('Order placement failed: ' + res.data.message)
      }
    } catch (err) {
      alert('Order failed: server communication error')
    } finally {
      setIsPlacingOrder(false)
    }
  }

  // Manual Exit Order
  const handleExitTrade = async (tradeId) => {
    if (!confirm('Are you sure you want to close this position?')) return
    try {
      const res = await api.post('/trade/exit', {
        trade_id: tradeId,
        reason: 'Manual Exit via Terminal UI'
      })
      if (res.data.success) {
        alert(`Position exited successfully! Realized PnL: ₹${res.data.data?.pnl}`)
        refreshAll()
      } else {
        alert('Exit failed: ' + res.data.message)
      }
    } catch (err) {
      alert('Exit failed: server communication error')
    }
  }

  // Refresh All Data Elements
  const refreshAll = async () => {
    await checkConnection()
    await fetchMarketData()
    await fetchTradeHistory()
    await fetchAnalytics()
    await fetchAutotradeStatus()
    await fetchSettings()
    await fetchLastDecision()
    if (activeTab === 'charts') {
      await fetchOptionChain(optionChainSymbol)
    }
  }

  // Refresh option chain when active tab or symbol changes
  useEffect(() => {
    if (activeTab === 'charts') {
      fetchOptionChain(optionChainSymbol)
    }
  }, [activeTab, optionChainSymbol])

  // Persist chat messages to localStorage whenever they change
  useEffect(() => {
    saveMessages(messages)
  }, [messages])

  // Persist active tab to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.ACTIVE_TAB, activeTab)
  }, [activeTab])

  // Mounting lifecycle
  useEffect(() => {
    const init = async () => {
      await refreshAll()
      setInitialLoading(false)
    }
    init()
    const interval = setInterval(() => {
      refreshAll()
    }, 15000) // 15 seconds refresh loop
    return () => clearInterval(interval)
  }, [])

  // Show a loading splash while we check if the backend session is still alive
  if (initialLoading) {
    return (
      <div style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        background: '#000000',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999
      }}>
        <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <img src={deltaLogo} alt="Delta Logo" style={{ height: '5.5rem', width: 'auto', display: 'block' }} />
          <div className="spinner" style={{ width: '2rem', height: '2rem', borderWidth: '3px', marginTop: '2rem' }}></div>
        </div>
      </div>
    )
  }

  return (
    <div className="container">
      {/* Upper Terminal Banner */}
      <header>
        <div className="logo-section">
          <img src={deltaLogo} alt="Delta Logo" className="header-logo" />
        </div>

        <div className="header-meta">
          {/* Server status */}
          <div className="status-badge">
            <span className="text-muted mobile-hide-inline">Terminal:</span>
            <div className={`status-dot ${isOnline ? 'online' : ''}`}></div>
            <span>
              <span className="mobile-hide-inline">{isOnline ? 'ONLINE' : 'OFFLINE'}</span>
              <span className="mobile-show-inline">{isOnline ? 'ON' : 'OFF'}</span>
            </span>
          </div>

          {/* Kotak Neo Auth Status */}
          <div className="status-badge">
            <span className="text-muted mobile-hide-inline">API:</span>
            <div className={`status-dot ${isAuthenticated ? 'online' : 'warning'}`}></div>
            <span>
              <span className="mobile-hide-inline">{isAuthenticated ? 'CONNECTED' : 'DISCONNECTED'}</span>
              <span className="mobile-show-inline">{isAuthenticated ? 'LIVE' : 'LOCK'}</span>
            </span>
          </div>

          {/* Autotrade Indicator */}
          <div className="status-badge" style={{ padding: '0.2rem 0.5rem' }}>
            <span className="text-muted mobile-hide-inline" style={{ marginRight: '0.25rem' }}>AutoTrade:</span>
            <button
              className={`btn ${autotradeEnabled ? '' : 'btn-secondary'} header-autotrade-btn`}
              style={{ width: 'auto', margin: 0, height: 'auto' }}
              onClick={() => toggleAutotrade(!autotradeEnabled)}
              disabled={isAutotradeToggling || !isAuthenticated}
            >
              {autotradeEnabled ? 'ACTIVE' : 'INACTIVE'}
            </button>
          </div>

          {/* Groq Rate Limit Warning */}
          {rateLimited && (
            <div className="status-badge" style={{ padding: '0.2rem 0.6rem', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '6px' }}>
              <div className="status-dot" style={{ background: '#ef4444', boxShadow: '0 0 6px #ef4444' }}></div>
              <span style={{ color: '#fca5a5', fontSize: '0.7rem', fontWeight: 600 }}>
                LLM LIMIT — {Math.floor(cooldownRemaining / 60)}m {cooldownRemaining % 60}s
              </span>
            </div>
          )}

          <button className="btn btn-secondary" style={{ width: 'auto', padding: '0.4rem' }} onClick={refreshAll} title="Sync Server Status">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
            </svg>
          </button>
        </div>
      </header>

      {/* Stats Indices Grid */}
      <div className="stats-grid">
        <div className={`stat stat-nifty ${niftyFlash}`}>
          <h3>Nifty 50</h3>
          <p>₹{parseFloat(marketData.nifty?.ltp).toFixed(2)}</p>
          <div className="sub">
            High: ₹{parseFloat(marketData.nifty?.high).toFixed(0)} | Low: ₹{parseFloat(marketData.nifty?.low).toFixed(0)}
          </div>
        </div>

        <div className={`stat stat-banknifty ${bankniftyFlash}`}>
          <h3>BankNifty</h3>
          <p>₹{parseFloat(marketData.banknifty?.ltp).toFixed(2)}</p>
          <div className="sub">
            High: ₹{parseFloat(marketData.banknifty?.high).toFixed(0)} | Low: ₹{parseFloat(marketData.banknifty?.low).toFixed(0)}
          </div>
        </div>

        <div className="stat stat-vix">
          <h3>India VIX</h3>
          <p>{marketData.india_vix?.vix ? parseFloat(marketData.india_vix.vix).toFixed(2) : '14.25'}</p>
          <div className="sub">Market Volatility Index</div>
        </div>

        <div className="stat stat-margin">
          <h3>Available Margin</h3>
          <p>₹{margin}</p>
          <div className="sub">Limits Net Capital</div>
        </div>
      </div>

      {/* Main Container Grid */}
      <div className="grid">

        {/* Left Column: AI Assistant Chat */}
        <div className="card chat-container">
          <div className="chat-header">
            <div className="chat-header-title">
              <span>DELTA S</span>
            </div>
            <span className="badge badge-blue">GPT-4 Scanner</span>
          </div>

          <div className="chat-messages">
            {messages.map((msg, index) => (
              <div key={index} className={`chat-message ${msg.sender}`}>
                <div
                  className="message-bubble"
                  dangerouslySetInnerHTML={{ __html: parseMarkdown(msg.text) }}
                ></div>
                <div className="message-time">
                  {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-area">
            <form onSubmit={(e) => { e.preventDefault(); handleSendMessage(); }} className="chat-input-row">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder={isAuthenticated ? "Type command or scan query..." : "Please log in using TOTP first..."}
                disabled={isSending}
              />
              <button
                type="submit"
                className="btn btn-send"
                disabled={isSending || !chatInput.trim()}
              >
                {isSending ? (
                  <div className="spinner"></div>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13"></line>
                    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                  </svg>
                )}
              </button>
            </form>

            <div className="chat-quick-actions">
              <button className="quick-action-btn" onClick={() => handleSendMessage('analyze nifty')} disabled={isSending || !isAuthenticated}>
                Scan Nifty
              </button>
              <button className="quick-action-btn" onClick={() => handleSendMessage('analyze banknifty')} disabled={isSending || !isAuthenticated}>
                Scan BankNifty
              </button>
              <button className="quick-action-btn" onClick={() => handleSendMessage('market overview')} disabled={isSending || !isAuthenticated}>
                Overview
              </button>
              <button className="quick-action-btn" onClick={() => handleSendMessage('show positions')} disabled={isSending || !isAuthenticated}>
                Positions
              </button>
              <button className="quick-action-btn" onClick={() => handleSendMessage('margin')} disabled={isSending || !isAuthenticated}>
                Limits
              </button>
              <button className="quick-action-btn" onClick={() => handleSendMessage('help')} disabled={isSending}>
                Help ?
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: Dashboard and Interactive Tab Panels */}
        <div className="dashboard-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, overflow: 'hidden' }}>
          {!isAuthenticated ? (
            <div className="lock-panel">
              <div className="lock-icon-container">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
              </div>
              <h3>Kotak Session Locked</h3>
              <p>Enter the 6-digit Google Authenticator TOTP token below to unlock live pricing, portfolio feeds, and options execution.</p>

              <form onSubmit={handleLogin} style={{ width: '100%', maxWidth: '300px' }}>
                <div className="form-group">
                  <input
                    type="text"
                    maxLength="6"
                    className="totp-input"
                    value={totp}
                    onChange={(e) => setTotp(e.target.value.replace(/[^0-9]/g, ''))}
                    placeholder="ENTER 6-DIGIT TOTP"
                    style={{ textAlign: 'center', fontSize: totp ? '1.25rem' : '0.8rem', letterSpacing: totp ? '0.3em' : '0.05em', fontFamily: totp ? 'var(--font-mono)' : 'var(--font-sans)' }}
                    disabled={isLoggingIn}
                  />
                </div>
                <button type="submit" className="btn btn-chamfer-bottom" disabled={isLoggingIn || totp.length !== 6}>
                  {isLoggingIn ? <div className="spinner"></div> : 'Establish Live Session'}
                </button>
              </form>
            </div>
          ) : (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, overflow: 'hidden', padding: '1.25rem' }}>
              <div className="tabs-navigation" style={{ overflowX: 'auto', whiteSpace: 'nowrap' }}>
                <button className={`tab-btn ${activeTab === 'positions' ? 'active' : ''}`} onClick={() => setActiveTab('positions')}>
                  Positions
                  <span className="tab-badge">{positions.length}</span>
                </button>
                <button className={`tab-btn ${activeTab === 'holdings' ? 'active' : ''}`} onClick={() => setActiveTab('holdings')}>
                  Holdings
                  <span className="tab-badge">{holdings.length}</span>
                </button>
                <button className={`tab-btn ${activeTab === 'charts' ? 'active' : ''}`} onClick={() => { setActiveTab('charts'); fetchOptionChain(optionChainSymbol); }}>
                  Option Chain
                </button>
                <button className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`} onClick={() => setActiveTab('history')}>
                  Trade Journal
                  <span className="tab-badge">{trades.length}</span>
                </button>
                <button className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`} onClick={() => setActiveTab('analytics')}>
                  Performance Stats
                </button>
                <button className={`tab-btn ${activeTab === 'manual' ? 'active' : ''}`} onClick={() => setActiveTab('manual')}>
                  Manual Order
                </button>
                <button className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`} onClick={() => setActiveTab('settings')}>
                  Risk Control
                </button>
              </div>

              {/* TAB 1: Positions */}
              {activeTab === 'positions' && (
                <div style={{ animation: 'fadeIn 0.25s ease-out', flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
                  {positions.length > 0 ? (
                    <div className="table-container">
                      <table>
                        <thead>
                          <tr>
                            <th>Trading Symbol</th>
                            <th>Segment</th>
                            <th>Quantity</th>
                            <th>Buy Avg</th>
                            <th>LTP</th>
                            <th>Net P&L</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {positions.map((p, idx) => {
                            const pnlVal = parseFloat(p.pnl)
                            return (
                              <tr key={idx}>
                                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: '700' }}>{p.tradingSymbol}</td>
                                <td><span className="badge badge-blue">{p.segment}</span></td>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>{p.qty}</td>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>₹{parseFloat(p.buyAvg).toFixed(2)}</td>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>₹{parseFloat(p.lastPrice).toFixed(2)}</td>
                                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: '700', color: pnlVal >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                                  ₹{pnlVal >= 0 ? '+' : ''}{pnlVal.toFixed(2)}
                                </td>
                                <td>
                                  {/* Check if trade exists in internal db to match exit trigger, or offer direct exit */}
                                  <button
                                    className="btn btn-red"
                                    style={{ width: 'auto', padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
                                    onClick={async () => {
                                      // Find corresponding trade in history that is open
                                      const matchedOpen = trades.find(t => t.status === 'OPEN' && (p.tradingSymbol.includes(t.symbol) || t.symbol.includes(p.symbol)))
                                      if (matchedOpen) {
                                        handleExitTrade(matchedOpen.id)
                                      } else {
                                        // Mock or generic order exit
                                        alert('This order was placed outside terminal database. Exit it using chat assistant or Kotak portal.')
                                      }
                                    }}
                                  >
                                    Exit
                                  </button>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-secondary)' }}>
                      <p>No open positions in current market session</p>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: Holdings */}
              {activeTab === 'holdings' && (
                <div style={{ animation: 'fadeIn 0.25s ease-out', flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
                  {holdings.length > 0 ? (
                    <div className="table-container">
                      <table>
                        <thead>
                          <tr>
                            <th>Symbol</th>
                            <th>Quantity</th>
                            <th>Avg Cost</th>
                            <th>LTP</th>
                            <th>Current Value</th>
                            <th>Profit/Loss</th>
                          </tr>
                        </thead>
                        <tbody>
                          {holdings.map((h, idx) => {
                            const avgPrice = parseFloat(h.buyAvg || h.avgCost || 0)
                            const ltpPrice = parseFloat(h.lastPrice || h.ltp || 0)
                            const qty = parseInt(h.qty || h.quantity || 0)
                            const curValue = qty * ltpPrice
                            const costValue = qty * avgPrice
                            const diff = curValue - costValue
                            const percent = costValue > 0 ? (diff / costValue) * 100 : 0

                            return (
                              <tr key={idx}>
                                <td style={{ fontWeight: '700' }}>{h.symbol || h.tradingSymbol}</td>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>{qty}</td>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>₹{avgPrice.toFixed(2)}</td>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>₹{ltpPrice.toFixed(2)}</td>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>₹{curValue.toFixed(2)}</td>
                                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: '700', color: diff >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                                  {diff >= 0 ? '+' : ''}₹{diff.toFixed(2)} ({percent.toFixed(2)}%)
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-secondary)' }}>
                      <p>No stock holdings found in portfolio</p>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: Historical Journal */}
              {activeTab === 'history' && (
                <div style={{ animation: 'fadeIn 0.25s ease-out', flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
                  {trades.length > 0 ? (
                    <div className="table-container" style={{ flex: 1, overflowY: 'auto' }}>
                      <table>
                        <thead>
                          <tr>
                            <th>Timestamp</th>
                            <th>Symbol</th>
                            <th>Option</th>
                            <th>Strike</th>
                            <th>Qty</th>
                            <th>Prices</th>
                            <th>Net P&L</th>
                            <th>Status</th>
                            <th>Type</th>
                            <th>Exit</th>
                          </tr>
                        </thead>
                        <tbody>
                          {trades.map((t, idx) => {
                            const dateObj = new Date(t.timestamp)
                            const timeStr = dateObj.toLocaleDateString() + ' ' + dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                            const pnlVal = parseFloat(t.pnl || 0)
                            return (
                              <tr key={t.id || idx}>
                                <td style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{timeStr}</td>
                                <td style={{ fontWeight: '700' }}>{t.symbol}</td>
                                <td>
                                  <span className={`badge ${t.option_type === 'CALL' || t.option_type === 'CE' ? 'badge-green' : 'badge-red'}`}>
                                    {t.option_type}
                                  </span>
                                </td>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>{t.strike}</td>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>{t.quantity}</td>
                                <td style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
                                  In: ₹{parseFloat(t.entry_price).toFixed(1)}
                                  {t.exit_price && ` | Out: ₹${parseFloat(t.exit_price).toFixed(1)}`}
                                </td>
                                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: '700', color: t.status === 'CLOSED' ? (pnlVal >= 0 ? 'var(--success)' : 'var(--danger)') : 'var(--text-muted)' }}>
                                  {t.status === 'CLOSED' ? `₹${pnlVal >= 0 ? '+' : ''}${pnlVal.toFixed(2)}` : 'OPEN'}
                                </td>
                                <td>
                                  <span className={`badge ${t.status === 'OPEN' ? 'badge-yellow' : 'badge-blue'}`}>
                                    {t.status}
                                  </span>
                                </td>
                                <td>
                                  <span className="badge badge-secondary" style={{ fontSize: '0.65rem' }}>
                                    {t.strategy || 'AI'}
                                  </span>
                                </td>
                                <td>
                                  {t.status === 'OPEN' && (
                                    <button
                                      className="btn btn-red"
                                      style={{ width: 'auto', padding: '0.2rem 0.5rem', fontSize: '0.75rem' }}
                                      onClick={() => handleExitTrade(t.id)}
                                    >
                                      Exit
                                    </button>
                                  )}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-secondary)' }}>
                      <p>No historical trades recorded in internal journal database.</p>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 4: Analytics Performance Metrics */}
              {activeTab === 'analytics' && (
                <div style={{ animation: 'fadeIn 0.25s ease-out', flex: 1, overflowY: 'auto', minHeight: 0 }}>
                  {analytics ? (
                    <div className="perf-grid">
                      <div className="perf-card">
                        <h4>Total Trades (All / Open)</h4>
                        <p className="perf-val-blue">{analytics.total_trades} <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>/ {analytics.open_trades} open</span></p>
                      </div>

                      <div className="perf-card">
                        <h4>Win Rate</h4>
                        <p className={`perf-val-green`}>{analytics.win_rate}%</p>
                      </div>

                      <div className="perf-card">
                        <h4>Net P&L</h4>
                        <p className={analytics.total_pnl >= 0 ? 'perf-val-green' : 'perf-val-red'}>
                          ₹{analytics.total_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </p>
                      </div>

                      <div className="perf-card">
                        <h4>Gross P&L</h4>
                        <p className={analytics.total_gross_pnl >= 0 ? 'perf-val-green' : 'perf-val-red'}>
                          ₹{analytics.total_gross_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </p>
                      </div>

                      <div className="perf-card">
                        <h4>Charges & Brokerage</h4>
                        <p className="perf-val-red">₹{analytics.total_charges.toFixed(2)}</p>
                      </div>

                      <div className="perf-card">
                        <h4>Profit Factor</h4>
                        <p className="perf-val-yellow">{analytics.profit_factor || '1.80'}</p>
                      </div>

                      <div className="perf-card">
                        <h4>Avg Win</h4>
                        <p className="perf-val-green">₹{analytics.avg_win.toFixed(1)}</p>
                      </div>

                      <div className="perf-card">
                        <h4>Avg Loss</h4>
                        <p className="perf-val-red">₹{analytics.avg_loss.toFixed(1)}</p>
                      </div>

                      <div className="perf-card">
                        <h4>Winners / Losers</h4>
                        <p className="perf-val-blue">
                          {analytics.winners} <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>wins</span> / {analytics.losers} <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>losses</span>
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-secondary)' }}>
                      <p>Trade journal is empty. Generate trades to see performance diagnostics.</p>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 5: Manual Order Form */}
              {activeTab === 'manual' && (
                <div style={{ animation: 'fadeIn 0.25s ease-out', maxWidth: '500px', margin: '0 auto', flex: 1, overflowY: 'auto', minHeight: 0, paddingRight: '0.5rem' }}>
                  <form onSubmit={handlePlaceManualOrder}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                      <div className="form-group">
                        <label>Asset Symbol</label>
                        <select value={manualSymbol} onChange={(e) => setManualSymbol(e.target.value)}>
                          <option value="NIFTY">NIFTY 50</option>
                          <option value="BANKNIFTY">BANKNIFTY</option>
                        </select>
                      </div>

                      <div className="form-group">
                        <label>Option Type</label>
                        <select value={manualOptionType} onChange={(e) => setManualOptionType(e.target.value)}>
                          <option value="CALL">CALL (CE)</option>
                          <option value="PUT">PUT (PE)</option>
                        </select>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                      <div className="form-group">
                        <label>Strike Price</label>
                        <input
                          type="number"
                          value={manualStrike}
                          onChange={(e) => setManualStrike(e.target.value)}
                          placeholder="e.g. 24350"
                        />
                      </div>

                      <div className="form-group">
                        <label>Expiry Date</label>
                        <input
                          type="text"
                          value={manualExpiry}
                          onChange={(e) => setManualExpiry(e.target.value)}
                          placeholder="YYYY-MM-DD"
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label>Quantity (Contracts)</label>
                      <input
                        type="number"
                        value={manualQty}
                        onChange={(e) => setManualQty(e.target.value)}
                        placeholder="e.g. 50"
                      />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                      <div className="form-group">
                        <label>Stop Loss (Optional Trigger)</label>
                        <input
                          type="number"
                          step="0.05"
                          value={manualSL}
                          onChange={(e) => setManualSL(e.target.value)}
                          placeholder="e.g. 95"
                        />
                      </div>

                      <div className="form-group">
                        <label>Target (Optional Trigger)</label>
                        <input
                          type="number"
                          step="0.05"
                          value={manualTarget}
                          onChange={(e) => setManualTarget(e.target.value)}
                          placeholder="e.g. 175"
                        />
                      </div>
                    </div>

                    <button
                      type="submit"
                      className="btn"
                      style={{ marginTop: '1rem' }}
                      disabled={isPlacingOrder}
                    >
                      {isPlacingOrder ? <div className="spinner"></div> : 'Dispatch Buy Order'}
                    </button>
                  </form>
                </div>
              )}

              {/* TAB 6: Option Chain */}
              {activeTab === 'charts' && (
                <div style={{ animation: 'fadeIn 0.25s ease-out', flex: 1, display: 'flex', flexDirection: 'column', gap: '0.75rem', minHeight: 0, overflow: 'hidden' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button
                        className={`btn ${optionChainSymbol === 'NIFTY' ? '' : 'btn-secondary'}`}
                        style={{ width: 'auto', padding: '0.35rem 0.8rem', fontSize: '0.8rem', margin: 0, height: 'auto' }}
                        onClick={() => {
                          setOptionChainSymbol('NIFTY')
                          fetchOptionChain('NIFTY')
                        }}
                      >
                        Nifty 50
                      </button>
                      <button
                        className={`btn ${optionChainSymbol === 'BANKNIFTY' ? '' : 'btn-secondary'}`}
                        style={{ width: 'auto', padding: '0.35rem 0.8rem', fontSize: '0.8rem', margin: 0, height: 'auto' }}
                        onClick={() => {
                          setOptionChainSymbol('BANKNIFTY')
                          fetchOptionChain('BANKNIFTY')
                        }}
                      >
                        BankNifty
                      </button>
                    </div>

                    <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                      Spot Price: <span style={{ fontWeight: '700', color: 'var(--primary)', fontFamily: 'var(--font-mono)' }}>₹{optionChainSpot.toFixed(2)}</span>
                    </div>
                  </div>

                  {isOptionChainLoading ? (
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '300px' }}>
                      <div className="spinner" style={{ width: '2rem', height: '2rem' }}></div>
                    </div>
                  ) : optionChainData.length > 0 ? (
                    <div className="table-container" style={{ maxHeight: '420px', overflowY: 'auto' }}>
                      <table style={{ textAlign: 'center' }}>
                        <thead>
                          <tr style={{ background: 'rgba(255,255,255,0.02)' }}>
                            <th colSpan="3" style={{ textAlign: 'center', borderRight: '1px solid var(--border-color)', color: 'var(--success)' }}>CALLS (CE)</th>
                            <th style={{ textAlign: 'center', borderRight: '1px solid var(--border-color)' }}>STRIKE</th>
                            <th colSpan="3" style={{ textAlign: 'center', color: 'var(--danger)' }}>PUTS (PE)</th>
                          </tr>
                          <tr>
                            <th>OI</th>
                            <th>Volume</th>
                            <th style={{ borderRight: '1px solid var(--border-color)' }}>LTP</th>
                            <th style={{ borderRight: '1px solid var(--border-color)' }}>Price</th>
                            <th>LTP</th>
                            <th>Volume</th>
                            <th>OI</th>
                          </tr>
                        </thead>
                        <tbody>
                          {optionChainData.map((row, idx) => {
                            const strike = row.strike
                            const ce = row.CE || {}
                            const pe = row.PE || {}

                            // Calculate ATM
                            const step = optionChainSymbol === 'NIFTY' ? 50 : 100
                            const atmStrike = Math.round(optionChainSpot / step) * step
                            const isAtm = strike === atmStrike

                            // ITM background tints
                            const ceItm = strike < optionChainSpot
                            const peItm = strike > optionChainSpot

                            const ceBg = ceItm ? 'rgba(0, 255, 102, 0.02)' : 'transparent'
                            const peBg = peItm ? 'rgba(255, 59, 48, 0.02)' : 'transparent'

                            return (
                              <tr key={idx} style={isAtm ? { background: 'rgba(255, 255, 255, 0.08)', borderTop: '1px solid var(--primary)', borderBottom: '1px solid var(--primary)' } : {}}>
                                {/* CE Columns */}
                                <td style={{ background: ceBg, fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                  {ce.oi?.toLocaleString('en-IN') || '-'}
                                </td>
                                <td style={{ background: ceBg, fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                  {ce.volume?.toLocaleString('en-IN') || '-'}
                                </td>
                                <td style={{ background: ceBg, fontFamily: 'var(--font-mono)', fontWeight: '700', borderRight: '1px solid var(--border-color)', color: 'var(--success)' }}>
                                  ₹{ce.ltp?.toFixed(2) || '-'}
                                </td>

                                {/* Strike Price Column */}
                                <td style={{ fontWeight: '800', borderRight: '1px solid var(--border-color)', color: isAtm ? 'var(--primary)' : 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                                  {strike}
                                </td>

                                {/* PE Columns */}
                                <td style={{ background: peBg, fontFamily: 'var(--font-mono)', fontWeight: '700', color: 'var(--danger)' }}>
                                  ₹{pe.ltp?.toFixed(2) || '-'}
                                </td>
                                <td style={{ background: peBg, fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                  {pe.volume?.toLocaleString('en-IN') || '-'}
                                </td>
                                <td style={{ background: peBg, fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                  {pe.oi?.toLocaleString('en-IN') || '-'}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-secondary)' }}>
                      <p>No options data available.</p>
                      <p style={{ fontSize: '0.75rem', marginTop: '0.5rem' }}>Make sure your Kotak Neo session is active to fetch real-time contract feeds.</p>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 7: Risk Control Panel */}
              {activeTab === 'settings' && (
                <div style={{ animation: 'fadeIn 0.25s ease-out', flex: 1, overflowY: 'auto', minHeight: 0, paddingRight: '0.5rem' }}>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 800, marginBottom: '1.25rem', color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>Beast Risk & Capital Parameters</h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: '550px' }}>

                    {/* Paper Trading Toggle */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '0.75rem 1rem', borderRadius: '0.5rem', border: '1px solid var(--border-color)' }}>
                      <div>
                        <span style={{ fontSize: '0.85rem', fontWeight: 700, display: 'block' }}>Simulated Paper Trading</span>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Intercept execution to trade with virtual capital (₹{margin})</span>
                      </div>
                      <button
                        type="button"
                        className="btn"
                        style={{
                          width: 'auto',
                          padding: '0.4rem 0.8rem',
                          fontSize: '0.75rem',
                          margin: 0,
                          height: 'auto',
                          background: settings.paper_trading ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                          border: `1px solid ${settings.paper_trading ? 'var(--success)' : 'var(--danger)'}`,
                          color: settings.paper_trading ? 'var(--success)' : 'var(--danger)'
                        }}
                        onClick={() => {
                          const updated = { ...settings, paper_trading: !settings.paper_trading };
                          setSettings(updated);
                        }}
                      >
                        {settings.paper_trading ? 'PAPER TRADING ON' : 'LIVE TRADING ON'}
                      </button>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                      <div className="form-group">
                        <label>Max Daily Loss (₹)</label>
                        <input
                          type="number"
                          value={settings.max_daily_loss}
                          onChange={(e) => setSettings({ ...settings, max_daily_loss: parseFloat(e.target.value) || 0 })}
                          placeholder="e.g. 1000"
                        />
                      </div>
                      <div className="form-group">
                        <label>Risk Per Trade (%)</label>
                        <input
                          type="number"
                          step="0.1"
                          value={settings.risk_percent}
                          onChange={(e) => setSettings({ ...settings, risk_percent: parseFloat(e.target.value) || 0 })}
                          placeholder="e.g. 2.0"
                        />
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                      <div className="form-group">
                        <label>Default Qty (Lots/Contracts)</label>
                        <input
                          type="number"
                          value={settings.default_quantity}
                          onChange={(e) => setSettings({ ...settings, default_quantity: parseInt(e.target.value) || 0 })}
                          placeholder="e.g. 50"
                        />
                      </div>
                      <div className="form-group">
                        <label>Min Risk:Reward Ratio</label>
                        <input
                          type="number"
                          step="0.1"
                          value={settings.min_risk_reward}
                          onChange={(e) => setSettings({ ...settings, min_risk_reward: parseFloat(e.target.value) || 0 })}
                          placeholder="e.g. 2.0"
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label>Max Parallel Open Trades</label>
                      <input
                        type="number"
                        value={settings.max_open_trades}
                        onChange={(e) => setSettings({ ...settings, max_open_trades: parseInt(e.target.value) || 0 })}
                        placeholder="e.g. 1"
                      />
                    </div>

                    <button
                      type="button"
                      className="btn"
                      style={{ marginTop: '0.5rem' }}
                      onClick={() => saveSettings(settings)}
                      disabled={isSavingSettings}
                    >
                      {isSavingSettings ? <div className="spinner"></div> : 'Apply & Save Config'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* AI Explainer Drawer overlay */}
      {drawerOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            background: 'rgba(0,0,0,0.6)',
            backdropFilter: 'blur(4px)',
            zIndex: 999
          }}
          onClick={() => setDrawerOpen(false)}
        >
          {/* Drawer Container */}
          <div
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              width: '420px',
              maxWidth: '100vw',
              height: '100vh',
              background: '#0a0a0a',
              borderLeft: '1px solid var(--border-color)',
              padding: '1.5rem',
              boxShadow: '-10px 0 30px rgba(0,0,0,0.5)',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
              zIndex: 1000,
              animation: 'slideIn var(--transition-normal) forwards'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
              <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--primary)' }}>AI Decisions Explainer</h2>
              <button
                className="btn btn-secondary"
                style={{ width: 'auto', padding: '0.25rem 0.5rem', fontSize: '0.75rem', margin: 0 }}
                onClick={() => setDrawerOpen(false)}
              >
                Close
              </button>
            </div>

            {/* Content */}
            <div style={{ flexGrow: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1.25rem', paddingRight: '0.25rem' }}>
              {lastDecision ? (
                <>
                  {/* Status card */}
                  <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '0.75rem', padding: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 700 }}>Signal for {lastDecision.symbol}</span>
                      <p style={{ margin: 0, fontSize: '1.15rem', fontWeight: 800, color: lastDecision.signal.includes('CALL') ? 'var(--success)' : lastDecision.signal.includes('PUT') ? 'var(--danger)' : 'var(--text-muted)' }}>
                        {lastDecision.signal}
                      </p>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                      <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 700 }}>Confidence</span>
                      <span style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--primary)', fontFamily: 'var(--font-mono)' }}>
                        {lastDecision.confidence}%
                      </span>
                    </div>
                  </div>

                  {/* Market Details */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                    <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-color)', borderRadius: '0.5rem', padding: '0.5rem 0.75rem' }}>
                      <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)' }}>INDEX SPOT</span>
                      <p style={{ margin: 0, fontSize: '0.9rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>₹{lastDecision.spot_price?.toFixed(2)}</p>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border-color)', borderRadius: '0.5rem', padding: '0.5rem 0.75rem' }}>
                      <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)' }}>INDIA VIX</span>
                      <p style={{ margin: 0, fontSize: '0.9rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{lastDecision.vix?.toFixed(2)}</p>
                    </div>
                  </div>

                  {/* Trend direction */}
                  <div>
                    <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 700, display: 'block', marginBottom: '0.25rem' }}>Trend Assessment</span>
                    <span className={`badge ${lastDecision.trend === 'BULLISH' ? 'badge-green' : lastDecision.trend === 'BEARISH' ? 'badge-red' : 'badge-yellow'}`} style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem' }}>
                      {lastDecision.trend}
                    </span>
                  </div>

                  {/* Reasoning text */}
                  <div>
                    <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', textTransform: 'uppercase', fontWeight: 700, display: 'block', marginBottom: '0.25rem' }}>AI Rationale</span>
                    <div style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '0.5rem', padding: '0.75rem 1rem', fontSize: '0.8rem', lineHeight: '1.45', color: '#e2e8f0', whiteSpace: 'pre-wrap' }}>
                      {lastDecision.reason}
                    </div>
                  </div>

                  {/* Time since calculation */}
                  <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textAlign: 'right' }}>
                    Checked: {new Date(lastDecision.timestamp).toLocaleTimeString()} ({new Date(lastDecision.timestamp).toLocaleDateString()})
                  </div>
                </>
              ) : (
                <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-secondary)' }}>
                  <p>No AI analysis records triggered yet.</p>
                  <p style={{ fontSize: '0.75rem', marginTop: '0.5rem' }}>Start the AutoTrade background scanner to capture live decisions.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
