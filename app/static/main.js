
// Global variables
let currentAnalysis = null;
let isAnalyzing = false;
let sseConnection = null;
let currentClientId = null;
const API_BASE = '';  // Flask server base URL

// 配置marked.js
if (typeof marked !== 'undefined') {
    marked.setOptions({
        breaks: true,
        gfm: true,
        sanitize: false,
        smartLists: true,
        smartypants: true
    });
}

// SSE连接管理
function initSSE() {
    if (sseConnection) {
        sseConnection.close();
    }

    currentClientId = generateClientId();
    const sseUrl = `${API_BASE}/sse/stream?client_id=${currentClientId}`;
    
    addLog('🌊 正在建立SSE连接...', 'info');
    
    sseConnection = new EventSource(sseUrl);
    
    sseConnection.onopen = function(event) {
        addLog('✅ SSE连接已建立', 'success');
        updateSSEStatus(true);
    };
    
    sseConnection.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            handleSSEMessage(data);
        } catch (e) {
            console.error('SSE消息解析失败:', e);
        }
    };
    
    sseConnection.onerror = function(event) {
        addLog('❌ SSE连接错误', 'error');
        updateSSEStatus(false);
        
        // 自动重连
        setTimeout(() => {
            if (!sseConnection || sseConnection.readyState === EventSource.CLOSED) {
                addLog('🔄 尝试重新连接SSE...', 'warning');
                initSSE();
            }
        }, 3000);
    };
    
    sseConnection.onclose = function(event) {
        addLog('🔌 SSE连接已关闭', 'warning');
        updateSSEStatus(false);
    };
}

function generateClientId() {
    return 'client_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
}

function updateSSEStatus(connected) {
    const indicator = document.getElementById('sseIndicator');
    const status = document.getElementById('sseStatus');
    
    if (connected) {
        indicator.classList.add('connected');
        status.textContent = 'SSE已连接';
    } else {
        indicator.classList.remove('connected');
        status.textContent = 'SSE断开';
    }
}

function handleSSEMessage(data) {
    const eventType = data.event;
    const eventData = data.data;
    
    switch (eventType) {
        case 'log':
            addLog(eventData.message, eventData.type || 'info');
            break;
            
        case 'progress':
            updateProgress(eventData.element_id, eventData.percent);
            if (eventData.message) {
                addLog(eventData.message, 'progress');
            }
            if (eventData.current_stock) {
                document.getElementById('currentStock').textContent = 
                    `正在分析: ${eventData.current_stock}`;
                document.getElementById('currentStock').style.display = 'block';
            }
            break;
            
        case 'scores_update':
            updateScoreCards(eventData.scores);
            if (eventData.animate) {
                animateScoreCards();
            }
            break;
            
        case 'data_quality_update':
            updateDataQuality(eventData);
            break;
            
        case 'partial_result':
            displayPartialResults(eventData);
            break;
            
        case 'final_result':
            displayResults(eventData);
            currentAnalysis = eventData;
            break;
            
        case 'batch_result':
            displayBatchResults(eventData);
            currentAnalysis = eventData;
            break;
            
        case 'analysis_complete':
            onAnalysisComplete(eventData);
            break;
            
        case 'analysis_error':
            onAnalysisError(eventData);
            break;
            
        case 'ai_stream':
            handleAIStream(eventData);
            break;

        case 'ai_prompt':
            setPromptContent(eventData.content);
            break
            
        case 'error':
            addLog(`⚠️ SSE错误: ${eventData.error || '未知错误'}`, 'warning');
            break;
            
        case 'heartbeat':
            // 心跳，不需要处理
            break;
            
        default:
            console.log('未知SSE事件:', eventType, eventData);
    }
}

function handleAIStream(data) {
    // 获取或创建AI流式显示区域
    let aiStreamDiv = document.getElementById('aiStreamContent');
    if (!aiStreamDiv) {
        const resultsContent = document.getElementById('resultsContent');
        
        // 如果没有找到结果区域，创建临时显示区域
        resultsContent.insertAdjacentHTML('beforeend', `
            <div style="line-height: 1.6;">
                <h2 style="color: #2c3e50; border-bottom: 2px solid #e9ecef; padding-bottom: 12px; margin-bottom: 20px;">
                    📈 实时分析进行中...
                    <span style="font-size: 12px; color: #28a745; font-weight: normal;">🌊 AI流式生成中</span>
                </h2>
                
                <div style="background: #fff3e0; padding: 20px; border-radius: 8px; border-left: 4px solid #ff9800;">
                    <h3 style="color: #f57c00; margin-bottom: 12px;">🤖 AI 深度分析 - 实时生成中...</h3>
                    <div id="aiStreamContent" style="color: #5d4037; font-size: 14px; line-height: 1.7; white-space: pre-wrap; word-wrap: break-word;"></div>
                </div>
            </div>
        `);
        aiStreamDiv = document.getElementById('aiStreamContent');
    }
    
    // 添加AI流式内容
    if (aiStreamDiv && data.content) {
        aiStreamDiv.textContent += data.content;
        
        // 自动滚动到底部
        aiStreamDiv.scrollTop = aiStreamDiv.scrollHeight;
        
        // 如果容器可见，也滚动到底部
        const resultsContent = document.getElementById('resultsContent');
        if (resultsContent) {
            resultsContent.scrollTop = resultsContent.scrollHeight;
        }
    }
}


function animateScoreCards() {
    const cards = document.querySelectorAll('.score-card');
    cards.forEach(card => {
        card.classList.add('updating');
        setTimeout(() => {
            card.classList.remove('updating');
        }, 1500);
    });
}

// Tab switching
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
    document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
    
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(tabName + 'Tab').classList.add('active');
}

// Log functions
function addLog(message, type = 'info') {
    const logDisplay = document.getElementById('logDisplay');
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    
    const timestamp = new Date().toLocaleTimeString();
    let icon = '📋';
    
    switch(type) {
        case 'success': icon = '✅'; break;
        case 'warning': icon = '⚠️'; break;
        case 'error': icon = '❌'; break;
        case 'header': icon = '🎯'; break;
        case 'progress': icon = '🔄'; break;
    }
    
    logEntry.innerHTML = `<span style="color: #999;">[${timestamp}]</span> ${icon} ${message}`;
    logDisplay.appendChild(logEntry);
    logDisplay.scrollTop = logDisplay.scrollHeight;
}

function clearLog() {
    document.getElementById('logDisplay').innerHTML = 
        '<div class="log-entry log-info">📋 日志已清空</div>';
}

// Progress bar functions
function showProgress(elementId, show = true) {
    const progressBar = document.getElementById(elementId);
    progressBar.style.display = show ? 'block' : 'none';
    if (!show) {
        progressBar.querySelector('.progress-bar-fill').style.width = '0%';
    }
}

function updateProgress(elementId, percent) {
    const fill = document.getElementById(elementId).querySelector('.progress-bar-fill');
    fill.style.width = percent + '%';
}

// Score card functions
function updateScoreCards(scores) {
    const cards = {
        comprehensive: document.getElementById('comprehensiveCard'),
        technical: document.getElementById('technicalCard'),
        fundamental: document.getElementById('fundamentalCard'),
        sentiment: document.getElementById('sentimentCard')
    };

    Object.keys(scores).forEach(key => {
        const card = cards[key];
        if (card) {
            const score = scores[key];
            card.querySelector('.score').textContent = score.toFixed(1);
            
            card.className = 'score-card';
            if (score >= 80) card.classList.add('excellent');
            else if (score >= 60) card.classList.add('good');
            else if (score >= 40) card.classList.add('average');
            else card.classList.add('poor');
        }
    });

    document.getElementById('scoreCards').style.display = 'grid';
}

function updateDataQuality(data) {
    document.getElementById('financialCount').textContent = 
        data.financial_indicators_count || 0;
    document.getElementById('newsCount').textContent = 
        data.total_news_count || 0;
    document.getElementById('completeness').textContent = 
        (data.analysis_completeness || '部分').substring(0, 2);
    
    document.getElementById('dataQuality').style.display = 'grid';
}

function showLoading(stockName) {
    document.getElementById('resultsContent').innerHTML = `
        <!-- 基本信息容器 永远显示 -->
        <div id="basicInfoContainer" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px;">
            <!-- 基本信息 -->
            <div style="background: #f8f9fa; padding: 16px; border-radius: 8px;">
                <h4 style="color: #495057; margin-bottom: 8px;">基本信息</h4>
                <p id="stockCodeDisplay">股票代码: --</p>
                <p id="currentPriceDisplay">当前价格: --</p>
                <p id="priceChangeDisplay">涨跌幅: --</p>
            </div>

            <!-- 技术指标 -->
            <div style="background: #f8f9fa; padding: 16px; border-radius: 8px;">
                <h4 style="color: #495057; margin-bottom: 8px;">技术指标</h4>
                <p id="rsiDisplay">RSI: --</p>
                <p id="trendDisplay">趋势: --</p>
                <p id="macdDisplay">MACD: --</p>
            </div>

            <!-- 市场情绪 -->
            <div style="background: #f8f9fa; padding: 16px; border-radius: 8px;">
                <h4 style="color: #495057; margin-bottom: 8px;">市场情绪</h4>
                <p id="sentimentTrendDisplay">情绪趋势: --</p>
                <p id="newsCountDisplay">新闻数量: --</p>
                <p id="confidenceDisplay">置信度: --</p>
            </div>

            <!-- 投资建议 -->
            <div style="background: #e3f2fd; padding: 16px; border-radius: 8px;">
                <h4 style="color: #495057; margin-bottom: 8px;">投资建议</h4>
                <p id="recommendationDisplay">暂无数据</p>
            </div>
        </div>

        <!-- LLM 选项卡 -->
        <div class="tab-container">
            <div class="tab-buttons">
                <button class="tab-btn" data-tab="llm-prompt">Prompt 查看</button>
                <button class="tab-btn active" data-tab="llm-results">LLM 分析结果</button>
            </div>

            <div class="llm-tab-content active" id="llm-results">
                <div id="aiStreamContainer">
                    <h3 style="color:#f57c00;">🤖 AI 深度分析 - 实时生成中...</h3>
                    <div id="aiStreamContent" style="color:#5d4037; font-size:14px; line-height:1.7; white-space:pre-wrap;"></div>
                </div>
            </div>

            <div class="llm-tab-content" id="llm-prompt">
                <p id="promptDisplay" style="color:#666;font-size:14px;">Prompt 将在分析完成后显示</p>
            </div>
        </div>
    `;

    initTabSwitching();
}


function initTabSwitching() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.llm-tab-content');

    tabButtons.forEach(btn => {
        btn.onclick = () => {
            const targetId = btn.dataset.tab;

            // 切换按钮样式
            tabButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // 显示对应 tab 内容
            tabContents.forEach(tc => {
                tc.id === targetId ? tc.classList.add('active') : tc.classList.remove('active');
            });
        };
    });
}

function setPromptContent(llmPrompt) {
    const promptTab = document.getElementById('llm-prompt');
    promptTab.innerHTML = parseMarkdown(llmPrompt);
    promptTab.classList.add('ai-analysis-content');
    promptTab.style.whiteSpace = 'normal';
}

function parseMarkdown(text) {
    if (typeof marked !== 'undefined') {
        return marked.parse(text);
    } else {
        return simpleMarkdownParse(text);
    }
}



function displayPartialResults(data) {
    if (data.type === 'basic_info') {
        // 基本信息
        document.getElementById('stockCodeDisplay').textContent = `股票代码: ${data.stock_code}`;
        document.getElementById('currentPriceDisplay').textContent = `当前价格: ¥${(data.current_price || 0).toFixed(2)}`;
        document.getElementById('priceChangeDisplay').textContent = `涨跌幅: ${(data.price_change || 0).toFixed(2)}%`;

        // 分析进度
        // 如果需要可以在 basicInfoContainer 里添加占位 p 标签，用于显示进度
        if (document.getElementById('progressTech')) document.getElementById('progressTech').textContent = '🔄 技术指标获取中...';
        if (document.getElementById('progressFinance')) document.getElementById('progressFinance').textContent = '⏳ 财务数据分析中...';
        if (document.getElementById('progressNews')) document.getElementById('progressNews').textContent = '🌊 新闻情绪处理中...';
    }
}


function displayResults(report) {
    // 检查是否有AI流式内容正在显示
    const existingAIStream = document.getElementById('aiStreamContent');
    let aiAnalysisHtml = '';
    
    if (existingAIStream && existingAIStream.textContent.trim()) {
        // 修改h3标题
        const streamTitle = existingAIStream.parentElement.querySelector('h3');
        if (streamTitle) {
            streamTitle.innerHTML = '🤖 AI 深度分析 <span style="color: #28a745; font-size: 12px;">✅ 生成完成</span>';
        }
        // 修改h2主标题
        const h2Title = existingAIStream.closest('div').querySelector('h2');
        if (h2Title) {
            h2Title.innerHTML = 'LLM 深度分析报告';
        }
        
        // 将流式内容转换为markdown格式
        const streamContent = existingAIStream.textContent;
        if (typeof marked !== 'undefined') {
            aiAnalysisHtml = marked.parse(streamContent);
        } else {
            aiAnalysisHtml = simpleMarkdownParse(streamContent);
        }
        
        // 更新AI分析区域
        existingAIStream.innerHTML = aiAnalysisHtml;
        existingAIStream.classList.add('ai-analysis-content');
        existingAIStream.style.whiteSpace = 'normal';
        
        // 保留现有的完整结果，只更新其他部分
        updateNonAIContent(report);
        return;
    }
}

function updateNonAIContent(report) {
    // 更新标题状态
    const statusEl = document.getElementById('analysisStatus');
    if (statusEl) statusEl.textContent = '✅ 流式分析完成';

    // 基本信息
    document.getElementById('stockCodeDisplay').textContent = `股票代码: ${report.stock_code}`;
    document.getElementById('currentPriceDisplay').textContent = `当前价格: ¥${(report.price_info?.current_price || 0).toFixed(2)}`;
    document.getElementById('priceChangeDisplay').textContent = `涨跌幅: ${(report.price_info?.price_change || 0).toFixed(2)}%`;

    // 技术指标
    document.getElementById('rsiDisplay').textContent = `RSI: ${(report.technical_analysis?.rsi || 0).toFixed(1)}`;
    document.getElementById('trendDisplay').textContent = `趋势: ${report.technical_analysis?.ma_trend || '未知'}`;
    document.getElementById('macdDisplay').textContent = `MACD: ${report.technical_analysis?.macd_signal || '未知'}`;

    // 市场情绪
    document.getElementById('sentimentTrendDisplay').textContent = `情绪趋势: ${report.sentiment_analysis?.sentiment_trend || '中性'}`;
    document.getElementById('newsCountDisplay').textContent = `新闻数量: ${report.sentiment_analysis?.total_analyzed || 0} 条`;
    document.getElementById('confidenceDisplay').textContent = `置信度: ${((report.sentiment_analysis?.confidence_score || 0) * 100).toFixed(1)}%`;

    // 投资建议
    document.getElementById('recommendationDisplay').textContent = report.recommendation || '数据不足';

    // LLM 流式内容
    if (report.ai_content) {
        const aiStream = document.getElementById('aiStreamContent');
        aiStream.textContent = report.ai_content;
        aiStream.scrollTop = aiStream.scrollHeight;
    }

    // Prompt
    if (report.prompt) {
        document.getElementById('promptDisplay').textContent = report.prompt;
    }

    // 显示导出按钮
    const exportBtn = document.getElementById('exportBtn');
    if (exportBtn) exportBtn.style.display = 'inline-flex';
}



// 简单的markdown解析器（备用方案）
function simpleMarkdownParse(text) {
    if (!text) return '';
    
    return text
        .replace(/^### (.*$)/gim, '<h3 style="color: #2c3e50; margin: 16px 0 8px 0;">$1</h3>')
        .replace(/^## (.*$)/gim, '<h2 style="color: #2c3e50; margin: 20px 0 10px 0;">$1</h2>')
        .replace(/^# (.*$)/gim, '<h1 style="color: #2c3e50; margin: 24px 0 12px 0;">$1</h1>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code style="background: #f1f3f4; padding: 2px 4px; border-radius: 3px; font-family: monospace;">$1</code>')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color: #1976d2;">$1</a>')
        .replace(/^[\-\*\+] (.*$)/gim, '<li style="margin: 4px 0;">$1</li>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');
}

function displayBatchResults(reports) {
    if (!reports || reports.length === 0) {
        addLog('批量分析结果为空', 'warning');
        return;
    }

    const avgScores = {
        comprehensive: reports.reduce((sum, r) => sum + r.scores.comprehensive, 0) / reports.length,
        technical: reports.reduce((sum, r) => sum + r.scores.technical, 0) / reports.length,
        fundamental: reports.reduce((sum, r) => sum + r.scores.fundamental, 0) / reports.length,
        sentiment: reports.reduce((sum, r) => sum + r.scores.sentiment, 0) / reports.length
    };

    updateScoreCards(avgScores);

    const avgFinancial = reports.reduce((sum, r) => sum + (r.data_quality?.financial_indicators_count || 0), 0) / reports.length;
    const avgNews = reports.reduce((sum, r) => sum + (r.sentiment_analysis?.total_analyzed || 0), 0) / reports.length;
    
    document.getElementById('financialCount').textContent = Math.round(avgFinancial);
    document.getElementById('newsCount').textContent = Math.round(avgNews);
    document.getElementById('completeness').textContent = '批量';
    document.getElementById('dataQuality').style.display = 'grid';

    const resultsContent = document.getElementById('resultsContent');
    
    let tableRows = reports
        .sort((a, b) => b.scores.comprehensive - a.scores.comprehensive)
        .map((report, index) => `
            <tr style="border-bottom: 1px solid #e9ecef;">
                <td style="padding: 12px; font-weight: 600;">${index + 1}</td>
                <td style="padding: 12px;">${report.stock_code}</td>
                <td style="padding: 12px;">${report.stock_name || report.stock_code}</td>
                <td style="padding: 12px; font-weight: 600; color: ${report.scores.comprehensive >= 70 ? '#27ae60' : report.scores.comprehensive >= 50 ? '#667eea' : '#e74c3c'};">
                    ${report.scores.comprehensive.toFixed(1)}
                </td>
                <td style="padding: 12px;">${report.scores.technical.toFixed(1)}</td>
                <td style="padding: 12px;">${report.scores.fundamental.toFixed(1)}</td>
                <td style="padding: 12px;">${report.scores.sentiment.toFixed(1)}</td>
                <td style="padding: 12px; font-weight: 600;">${report.recommendation}</td>
            </tr>
        `).join('');

    const html = `
        <div style="line-height: 1.6;">
            <h2 style="color: #2c3e50; border-bottom: 2px solid #e9ecef; padding-bottom: 12px; margin-bottom: 20px;">
                📊 批量分析报告 (${reports.length} 只股票)
                <span style="font-size: 12px; color: #28a745; font-weight: normal;">✅ 流式分析完成</span>
            </h2>
            
            <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin-bottom: 20px;">
                <h4 style="color: #495057; margin-bottom: 12px;">📋 分析汇总</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px;">
                    <div><strong>分析数量:</strong> ${reports.length} 只</div>
                    <div><strong>平均得分:</strong> ${avgScores.comprehensive.toFixed(1)}</div>
                    <div><strong>优秀股票:</strong> ${reports.filter(r => r.scores.comprehensive >= 80).length} 只</div>
                    <div><strong>良好股票:</strong> ${reports.filter(r => r.scores.comprehensive >= 60).length} 只</div>
                </div>
            </div>
            
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <thead>
                        <tr style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">
                            <th style="padding: 16px; text-align: left;">排名</th>
                            <th style="padding: 16px; text-align: left;">代码</th>
                            <th style="padding: 16px; text-align: left;">名称</th>
                            <th style="padding: 16px; text-align: left;">综合得分</th>
                            <th style="padding: 16px; text-align: left;">技术面</th>
                            <th style="padding: 16px; text-align: left;">基本面</th>
                            <th style="padding: 16px; text-align: left;">情绪面</th>
                            <th style="padding: 16px; text-align: left;">投资建议</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tableRows}
                    </tbody>
                </table>
            </div>
        </div>
    `;
    
    resultsContent.innerHTML = html;
    document.getElementById('exportBtn').style.display = 'inline-flex';
}

function onAnalysisComplete(data) {
    isAnalyzing = false;
    document.getElementById('analyzeBtn').disabled = false;
    document.getElementById('batchAnalyzeBtn').disabled = false;
    document.getElementById('systemStatus').className = 'status-indicator status-ready';
    document.getElementById('systemStatus').textContent = '系统就绪';
    showProgress('singleProgress', false);
    showProgress('batchProgress', false);
    document.getElementById('currentStock').style.display = 'none';
    
    addLog('✅ 分析完成', 'success');
}

function onAnalysisError(data) {
    isAnalyzing = false;
    document.getElementById('analyzeBtn').disabled = false;
    document.getElementById('batchAnalyzeBtn').disabled = false;
    document.getElementById('systemStatus').className = 'status-indicator status-error';
    document.getElementById('systemStatus').textContent = '分析失败';
    showProgress('singleProgress', false);
    showProgress('batchProgress', false);
    document.getElementById('currentStock').style.display = 'none';
    
    document.getElementById('resultsContent').innerHTML = `
        <div class="empty-state">
            <h3>❌ 分析失败</h3>
            <p>${data.error || '未知错误'}</p>
        </div>
    `;
    
    addLog(`❌ 分析失败: ${data.error}`, 'error');
}

// Analysis functions with SSE support
async function analyzeSingleStock() {
    const stockCode = document.getElementById('stockCode').value.trim();
    let positionPercent = document.getElementById('positionPercent').value;
    let avgPrice = document.getElementById('avgPrice').value;
    if (!stockCode) {
        addLog('请输入股票代码', 'warning');
        return;
    }
    if (!positionPercent) {
        addLog('默认未买入');
        positionPercent = 0;
        avgPrice = -1;
    }
    else if (positionPercent > 0) {
        if (!avgPrice) {
            addLog('请输入持仓均价', 'warning');
            return;
        }
    }

    if (isAnalyzing) {
        addLog('分析正在进行中，请稍候', 'warning');
        return;
    }

    isAnalyzing = true;
    document.getElementById('analyzeBtn').disabled = true;
    document.getElementById('systemStatus').className = 'status-indicator status-analyzing';
    document.getElementById('systemStatus').textContent = '分析中';

    addLog(`🚀 开始流式分析股票: ${stockCode}`, 'header');
    showLoading();
    showProgress('singleProgress');

    try {
        const response = await fetch(`${API_BASE}/analyze/streaming`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                stock_code: stockCode,
                positionPercent: positionPercent,
                avgPrice: avgPrice,
                enable_streaming: document.getElementById('enableStreaming').checked,
                client_id: currentClientId
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.error || '分析失败');
        }

    } catch (error) {
        onAnalysisError({error: error.message});
    }
}

async function analyzeBatchStocks() {
    const stockListText = document.getElementById('stockList').value.trim();
    if (!stockListText) {
        addLog('请输入股票代码列表', 'warning');
        return;
    }

    if (isAnalyzing) {
        addLog('分析正在进行中，请稍候', 'warning');
        return;
    }

    const stockList = stockListText.split('\n').map(s => s.trim()).filter(s => s);
    if (stockList.length === 0) {
        addLog('股票代码列表为空', 'warning');
        return;
    }

    isAnalyzing = true;
    document.getElementById('batchAnalyzeBtn').disabled = true;
    document.getElementById('systemStatus').className = 'status-indicator status-analyzing';
    document.getElementById('systemStatus').textContent = '批量分析中';

    addLog(`📊 开始流式批量分析 ${stockList.length} 只股票`, 'header');
    showLoading();
    showProgress('batchProgress');
    document.getElementById('currentStock').style.display = 'block';

    try {
        const response = await fetch(`${API_BASE}/analyze/batch_streaming`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                stock_codes: stockList,
                client_id: currentClientId
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.error || '批量分析失败');
        }

    } catch (error) {
        onAnalysisError({error: error.message});
    }
}

// Configuration (保持不变)
function showConfig() {
    addLog('⚙️ 打开配置对话框', 'info');
    
    fetch(`${API_BASE}/status/system_info`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const apis = data.data.configured_apis || [];
                const versions = data.data.api_versions || {};
                const primary = data.data.primary_api || 'openai';
                
                let configInfo = `🔧 Enhanced v3.0-Web-SSE AI配置状态

🎯 当前系统状态：
✅ 高并发：${data.data.max_workers}个工作线程
✅ 活跃任务：${data.data.active_tasks}个
`;

                alert(configInfo);
            }
        })
        .catch(error => {
            const fallbackInfo = `🔧 Enhanced v3.0-Web-SSE AI配置管理

❌ 无法获取当前配置状态，请检查服务器连接

📋 基本配置方法：
1. 在项目目录创建或编辑 config.json
2. 填入AI API密钥
3. 重启服务器

🌊 新特性：支持SSE实时流式推送

💡 如需帮助，请查看控制台日志`;
            alert(fallbackInfo);
        });
}

// Export report (保持不变，但添加SSE标识)
function exportReport() {
    if (!currentAnalysis) {
        addLog('⚠️ 没有可导出的报告', 'warning');
        return;
    }

    try {
        addLog('📤 开始导出分析报告...', 'info');
        
        const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
        let content, filename, reportType;

        if (Array.isArray(currentAnalysis)) {
            reportType = `批量分析(${currentAnalysis.length}只股票)`;
            filename = `batch_analysis_sse_${timestamp}.md`;
            content = generateBatchMarkdown(currentAnalysis);
        } else {
            reportType = `单个股票(${currentAnalysis.stock_code})`;
            filename = `stock_analysis_sse_${currentAnalysis.stock_code}_${timestamp}.md`;
            content = generateSingleMarkdown(currentAnalysis);
        }

        const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);

        addLog(`✅ ${reportType}报告导出成功: ${filename}`, 'success');
        
        const fileSize = (content.length / 1024).toFixed(1);
        setTimeout(() => {
            alert(`SSE流式分析报告已导出！\\n\\n📄 文件名：${filename}\\n📊 报告类型：${reportType}\\n📏 文件大小：${fileSize} KB\\n🌊 分析方式：SSE实时流式推送\\n🔧 分析器：Enhanced v3.0-Web-SSE | WebStockAnalyzer`);
        }, 100);

    } catch (error) {
        const errorMsg = `导出失败：${error.message}`;
        addLog(`❌ ${errorMsg}`, 'error');
        alert(errorMsg);
    }
}

function generateSingleMarkdown(report) {
    const aiAnalysis = report.ai_analysis || '分析数据准备中...';
    
    return `# 📈 股票分析报告 (Enhanced v3.0-Web-SSE)

## 🏢 基本信息
| 项目 | 值 |
|------|-----|
| **股票代码** | ${report.stock_code} |
| **股票名称** | ${report.stock_name} |
| **分析时间** | ${report.analysis_date} |
| **当前价格** | ¥${report.price_info.current_price.toFixed(2)} |
| **价格变动** | ${report.price_info.price_change.toFixed(2)}% |

## 📊 综合评分

### 🎯 总体评分：${report.scores.comprehensive.toFixed(1)}/100

| 维度 | 得分 | 评级 |
|------|------|------|
| **技术分析** | ${report.scores.technical.toFixed(1)}/100 | ${getScoreRating(report.scores.technical)} |
| **基本面分析** | ${report.scores.fundamental.toFixed(1)}/100 | ${getScoreRating(report.scores.fundamental)} |
| **情绪分析** | ${report.scores.sentiment.toFixed(1)}/100 | ${getScoreRating(report.scores.sentiment)} |

## 🎯 投资建议

### ${report.recommendation}

## 🤖 AI综合分析

${aiAnalysis}

---
*报告生成时间：${new Date().toLocaleString('zh-CN')}*  
*分析器版本：Enhanced v3.0-Web-SSE*  
*分析器类：WebStockAnalyzer (SSE流式版)*  
*推送方式：Server-Sent Events 实时流式*  
*数据来源：多维度综合分析*
`;
}

function generateBatchMarkdown(reports) {
    let content = `# 📊 批量股票分析报告 - Enhanced v3.0-Web-SSE

**分析时间：** ${new Date().toLocaleString('zh-CN')}
**分析数量：** ${reports.length} 只股票
**分析器版本：** Enhanced v3.0-Web-SSE
**分析器类：** WebStockAnalyzer (SSE流式版)
**推送方式：** Server-Sent Events 实时流式

## 📋 分析汇总

| 排名 | 股票代码 | 股票名称 | 综合得分 | 技术面 | 基本面 | 情绪面 | 投资建议 |
|------|----------|----------|----------|--------|--------|--------|----------|
`;

    reports.sort((a, b) => b.scores.comprehensive - a.scores.comprehensive)
            .forEach((report, index) => {
        content += `| ${index + 1} | ${report.stock_code} | ${report.stock_name} | ${report.scores.comprehensive.toFixed(1)} | ${report.scores.technical.toFixed(1)} | ${report.scores.fundamental.toFixed(1)} | ${report.scores.sentiment.toFixed(1)} | ${report.recommendation} |\n`;
    });

    content += `\n## 📈 详细分析\n\n`;
    
    reports.forEach(report => {
        content += generateSingleMarkdown(report);
        content += '\n---\n\n';
    });

    return content;
}

function getScoreRating(score) {
    if (score >= 80) return '优秀';
    if (score >= 60) return '良好';
    if (score >= 40) return '一般';
    return '较差';
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    
    // 初始化SSE连接
    initSSE();
    
    // 检查服务器连接和系统信息
    fetch(`${API_BASE}/status/system_info`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addLog('✅ 后端服务器连接成功', 'success');
                addLog(`🔧 系统状态：${data.data.active_tasks} 个活跃任务`, 'info');
                addLog(`🧵 线程池：${data.data.max_workers} 个工作线程`, 'info');
                
                addLog(`🤖 AI API已配置: ${data.data.primary_api}`, 'success');
                
                addLog('🚀 支持完整AI深度分析', 'success');
            }
        })
        .catch(error => {
            addLog('❌ 后端服务器连接失败，请检查服务器状态', 'error');
        });
});

// 页面卸载时关闭SSE连接
window.addEventListener('beforeunload', function() {
    if (sseConnection) {
        sseConnection.close();
    }
});