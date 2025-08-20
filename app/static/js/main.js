
// Global variables
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
    
    addLog('正在建立SSE连接...', 'info');
    
    sseConnection = new EventSource(sseUrl);
    
    sseConnection.onopen = function(event) {
        addLog('SSE连接已建立', 'success');
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
        addLog('SSE连接错误', 'error');
        updateSSEStatus(false);
        
        // 自动重连
        setTimeout(() => {
            if (!sseConnection || sseConnection.readyState === EventSource.CLOSED) {
                addLog('尝试重新连接SSE...', 'warning');
                initSSE();
            }
        }, 3000);
    };
    
    sseConnection.onclose = function(event) {
        addLog('SSE连接已关闭', 'warning');
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
            
        case 'data_quality_update':
            updateDataQuality(eventData);
            break;
            
        case 'partial_result':
            displayPartialResults(eventData);
            break;
            
        case 'final_result':
            displayResults(eventData);
            break;
            
        case 'batch_result':
            showBatchSlot(eventData);
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
            setPromptContent(eventData.element_id, eventData.content);
            break
            
        case 'error':
            addLog(`SSE错误: ${eventData.error || '未知错误'}`, 'warning');
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

// Tab switching
function switchTab(tabName) {
    // 切换tab按钮状态
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
    document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
    
    // 切换左侧面板中的内容
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(tabName + 'Tab').classList.add('active');

    // 切换右侧面板中的内容
    document.querySelectorAll('.results-panel').forEach(panel => panel.classList.remove('active'));
    document.getElementById(tabName + 'Results').classList.add('active');
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
        case 'info': icon = 'ℹ️'; break;
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

function updateDataQuality(data) {
    document.getElementById('financialCount').textContent = 
        data.financial_indicators_count || 0;
    document.getElementById('newsCount').textContent = 
        data.total_news_count || 0;
    document.getElementById('completeness').textContent = 
        (data.analysis_completeness || '部分').substring(0, 2);
    
    document.getElementById('dataQuality').style.display = 'grid';
}

function showLoading() {
    fetch("/static/html/result_content.html")
        .then(response => response.text())
        .then(html => {
            document.getElementById("resultsContent").innerHTML = html;
            initTabSwitching();
        })
        .catch(err => {
            console.error("加载失败:", err);
            addLog("result_content.html 加载失败");
        });
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

function setPromptContent(element_id, llmPrompt) {
    const promptTab = document.getElementById(element_id);
    promptTab.innerHTML = parseMarkdown(llmPrompt);
    promptTab.classList.add('ai-analysis-content');
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
        aiAnalysisHtml = parseMarkdown(streamContent);
        
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

    // LLM 流式内容
    if (report.ai_content) {
        const aiStream = document.getElementById('aiStreamContent');
        aiStream.textContent = report.ai_content;
        aiStream.scrollTop = aiStream.scrollHeight;
    }
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
    let positionPercent = parseFloat(document.getElementById('positionPercent').value);
    let avgPrice = parseFloat(document.getElementById('avgPrice').value);
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

    for (let i = 0; i < 10; i++) {
        const slot = document.getElementById(`batchSlot${i}`);
        if (slot) {
            slot.classList.add("hidden");
        }
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

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    
    // 初始化SSE连接
    initSSE();
    
    // 检查服务器连接和系统信息
    fetch(`${API_BASE}/status/system_info`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addLog('后端服务器连接成功', 'success');
                addLog(`系统状态：${data.data.active_tasks} 个活跃任务`, 'info');
                addLog(`线程池：${data.data.max_workers} 个工作线程`, 'info');
                
                addLog(`AI API已配置: ${data.data.primary_api}`, 'success');
                
                addLog('支持完整AI深度分析', 'success');
            }
        })
        .catch(error => {
            addLog(`后端服务器连接失败，请检查服务器状态 ${error}`, 'error');
        });
});

// 页面卸载时关闭SSE连接
window.addEventListener('beforeunload', function() {
    if (sseConnection) {
        sseConnection.close();
    }
});

function toggleSlot(index) {
    const body = document.getElementById(`slotBody${index}`);
    body.classList.toggle("hidden");
}

function showBatchSlot(eventData) {
    const index = eventData.index;
    const report = eventData.report;

    const slot = document.getElementById(`batchSlot${index}`);
    const title = document.getElementById(`slotTitle${index}`);
    const financial = document.getElementById(`financialCountBatch${index}`);
    const news = document.getElementById(`newsCountBatch${index}`);
    const completeness = document.getElementById(`completenessBatch${index}`);
    const content = document.getElementById(`batchResultsContent${index}`);

    // 设置标题
    title.textContent = `${index+1}. ${report.stock_name}`;

    // 显示槽位
    slot.classList.remove("hidden");

    // 填充数据
    financial.textContent = report.data_quality.financial_indicators_count || "--";
    news.textContent = report.data_quality.total_news_count || "--";
    completeness.textContent = report.data_quality.analysis_completeness || "--";

    content.innerHTML = `<!-- 基本信息容器 永远显示 -->
<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px;">
    <!-- 基本信息 -->
    <div style="background: #f8f9fa; padding: 16px; border-radius: 8px;">
        <h4 style="color: #495057; margin-bottom: 8px;">基本信息</h4>
        <p>股票代码: ${report.stock_code}</p>
        <p>当前价格: ${report.price_info.current_price}</p>
        <p>涨跌幅: ${report.price_info.price_change}</p>
    </div>

    <!-- 技术指标 -->
    <div style="background: #f8f9fa; padding: 16px; border-radius: 8px;">
        <h4 style="color: #495057; margin-bottom: 8px;">技术指标</h4>
        <p>RSI: ${report.technical_analysis.rsi}</p>
        <p>趋势: ${report.technical_analysis.ma_trend}</p>
        <p>MACD: ${report.technical_analysis.macd_signal}</p>
    </div>

    <!-- 市场情绪 -->
    <div style="background: #f8f9fa; padding: 16px; border-radius: 8px;">
        <h4 style="color: #495057; margin-bottom: 8px;">市场情绪</h4>
        <p>情绪趋势: ${report.sentiment_analysis?.sentiment_trend}</p>
        <p>新闻数量: ${report.sentiment_analysis?.total_analyzed}</p>
        <p>置信度: ${report.sentiment_analysis?.confidence_score}</p>
    </div>
</div>

<!-- LLM 选项卡 -->
<div class="tab-container" id="tabContainer${index}">
    <div class="tab-buttons">
        <button class="tab-btn active" data-tab="value-prompt-${index}">价值分析 Prompt 查看</button>
        <button class="tab-btn" data-tab="llm-prompt-${index}">总结 Prompt 查看</button>
        <button class="tab-btn" data-tab="llm-results-${index}">LLM 总结</button>
    </div>

    <div class="llm-tab-content active" id="value-prompt-${index}">
        <div class="ai-analysis-content">${parseMarkdown(report.value_prompt)}</div>
    </div>

    <div class="llm-tab-content" id="llm-prompt-${index}">
        <div class="ai-analysis-content">${parseMarkdown(report.prompt)}</div>
    </div>

    <div class="llm-tab-content" id="llm-results-${index}">
        <h3 style="color:#f57c00;">🤖 AI 深度分析</h3>
        <div class="ai-analysis-content">${parseMarkdown(report.ai_analysis)}</div>
    </div>
</div>`;
    // 为当前槽位的按钮加事件
    const container = document.getElementById(`tabContainer${index}`);
    const buttons = container.querySelectorAll(".tab-btn");
    const contents = container.querySelectorAll(".llm-tab-content");

    buttons.forEach(btn => {
        btn.addEventListener("click", () => {
            // 取消所有按钮和内容的 active
            buttons.forEach(b => b.classList.remove("active"));
            contents.forEach(c => c.classList.remove("active"));

            // 激活当前按钮
            btn.classList.add("active");

            // 显示对应内容
            const targetId = btn.getAttribute("data-tab");
            document.getElementById(targetId).classList.add("active");
        });
    });
}