<script setup>
import { computed, ref } from 'vue'
import { Activity, AlertCircle, ArrowRight, Check, ChevronRight, CircleAlert, Clock3, Download, ExternalLink, FileCode2, GitBranch, Github, LoaderCircle, Search, ShieldAlert } from 'lucide-vue-next'

const url = ref('')
const loading = ref(false)
const error = ref('')
const report = ref(null)
const activeTab = ref('overview')
const severityFilter = ref('all')

const severityNames = { critical: '紧急', high: '高', medium: '中', low: '低' }
const visibleFindings = computed(() => report.value?.findings.filter(item => severityFilter.value === 'all' || item.severity === severityFilter.value) || [])
const severityCounts = computed(() => Object.fromEntries(['critical', 'high', 'medium', 'low'].map(level => [level, report.value?.findings.filter(item => item.severity === level).length || 0])))
const scanDate = computed(() => report.value ? new Date(report.value.scannedAt).toLocaleString('zh-CN', { hour12: false }) : '')

async function scan() {
  error.value = ''
  report.value = null
  if (!url.value.trim()) { error.value = '请输入 GitHub 仓库链接。'; return }
  loading.value = true
  try {
    const response = await fetch('/api/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url.value.trim() }) })
    const data = await response.json()
    if (!response.ok) throw new Error(data.error || '扫描失败，请稍后重试。')
    report.value = data
    activeTab.value = 'overview'
    severityFilter.value = 'all'
  } catch (cause) {
    error.value = cause.message || '无法连接检测服务。'
  } finally {
    loading.value = false
  }
}

function downloadReport() {
  if (!report.value) return
  const blob = new Blob([JSON.stringify(report.value, null, 2)], { type: 'application/json' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${report.value.repository.owner}-${report.value.repository.repo}-readiness.json`
  link.click()
  URL.revokeObjectURL(link.href)
}
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar-inner">
        <div class="brand"><span class="brand-mark"><Activity :size="18" :stroke-width="2.5" /></span><span>接入体检</span><span class="brand-divider"></span><span class="brand-sub">Git 仓库就绪度</span></div>
        <span class="topbar-label"><span class="live-dot"></span> PUBLIC REPOSITORY SCAN</span>
      </div>
    </header>

    <main class="main">
      <section class="intro">
        <div class="intro-kicker"><span class="kicker-line"></span> REPOSITORY READINESS</div>
        <h1>让代码仓库，<br><span>做好接入准备。</span></h1>
        <p>输入公开 GitHub 仓库链接，检查文档、依赖、启动方式和敏感信息风险。</p>
      </section>

      <form class="scan-form" @submit.prevent="scan">
        <label for="repo-url">GitHub 仓库地址</label>
        <div class="input-row"><Github :size="21" /><input id="repo-url" v-model="url" type="url" placeholder="https://github.com/owner/repository" autocomplete="url" spellcheck="false" :disabled="loading" /><button type="submit" :disabled="loading"><LoaderCircle v-if="loading" :size="18" class="spin" /><Search v-else :size="18" /><span>{{ loading ? '正在检测' : '开始体检' }}</span><ArrowRight v-if="!loading" :size="17" /></button></div>
        <p v-if="error" class="form-error" role="alert"><CircleAlert :size="16" />{{ error }}</p>
        <p v-else class="form-note">仅支持公开仓库。扫描过程只读取文件，不执行仓库代码。</p>
      </form>

      <div v-if="loading" class="loading-state" role="status"><LoaderCircle :size="23" class="spin" /><div><strong>正在读取仓库</strong><span>检查默认分支、文件树和重点文件，通常需要几十秒。</span></div></div>

      <template v-if="report">
        <section class="report-head">
          <div class="report-title"><span class="eyebrow">ASSESSMENT REPORT</span><div class="report-title-row"><h2>{{ report.repository.owner }} <span>/</span> {{ report.repository.repo }}</h2><a :href="report.repository.url" target="_blank" rel="noopener noreferrer" title="在 GitHub 打开仓库" aria-label="在 GitHub 打开仓库"><ExternalLink :size="18" /></a></div><p>{{ report.repository.description || '公开 GitHub 仓库' }}</p><div class="report-meta"><span><GitBranch :size="14" /> {{ report.repository.defaultBranch }}</span><a :href="`${report.repository.url}/commit/${report.repository.commit}`" target="_blank" rel="noopener noreferrer" :title="`查看 commit ${report.repository.commit}`">commit {{ report.repository.commit.slice(0, 7) }}</a><span><Clock3 :size="14" /> {{ scanDate }}</span></div></div>
          <div class="score-block" :class="{ 'score-low': report.score < 60, 'score-mid': report.score >= 60 && report.score < 85 }"><div class="score-number">{{ report.score }}<span>/ 100</span></div><div class="score-caption"><span class="score-dot"></span>{{ report.readiness }}</div></div>
        </section>

        <div class="report-tabs"><div class="tabs" role="tablist" aria-label="报告视图"><button type="button" role="tab" :aria-selected="activeTab === 'overview'" :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">概览</button><button type="button" role="tab" :aria-selected="activeTab === 'findings'" :class="{ active: activeTab === 'findings' }" @click="activeTab = 'findings'">风险清单 <span>{{ report.findings.length }}</span></button></div><button class="download-btn" type="button" @click="downloadReport"><Download :size="16" /> 导出 JSON</button></div>

        <div v-if="activeTab === 'overview'" class="overview-view">
          <div class="section-heading"><div><span class="eyebrow">01 / CHECKPOINTS</span><h3>检测项目</h3></div><span>{{ report.categories.filter(item => item.status === 'checked').length }} / {{ report.categories.length }} 项通过</span></div>
          <div class="category-list"><button v-for="category in report.categories" :key="category.key" type="button" class="category-row" @click="activeTab = 'findings'"><span class="category-icon" :class="category.status"><Check v-if="category.status === 'checked'" :size="16" /><AlertCircle v-else :size="16" /></span><span class="category-main"><strong>{{ category.label }}</strong><small>{{ category.items.length ? category.items.slice(0, 2).join(' · ') : '未发现相关文件或特征' }}</small></span><span class="category-status" :class="category.status">{{ category.status === 'checked' ? '已检查' : '需关注' }}</span><ChevronRight :size="17" class="category-arrow" /></button></div>
          <div class="advice"><div class="advice-label"><ShieldAlert :size="17" /> 接入建议</div><p>{{ report.advice }}</p></div>
        </div>

        <div v-else class="findings-view"><div class="section-heading"><div><span class="eyebrow">02 / FINDINGS</span><h3>主要风险清单</h3></div><span>按严重程度排序</span></div><div class="filters" aria-label="按严重程度筛选"><button v-for="option in ['all', 'critical', 'high', 'medium', 'low']" :key="option" type="button" :class="{ selected: severityFilter === option }" @click="severityFilter = option">{{ option === 'all' ? '全部' : severityNames[option] }} <span>{{ option === 'all' ? report.findings.length : severityCounts[option] }}</span></button></div><div v-if="!visibleFindings.length" class="empty-findings"><Check :size="22" /><strong>当前筛选无风险项</strong><span>仍需结合实际部署环境人工核查。</span></div><div v-else class="finding-list"><article v-for="item in visibleFindings" :key="item.id" class="finding"><span class="severity" :class="item.severity">{{ severityNames[item.severity] }}</span><div><h4>{{ item.title }}</h4><p>{{ item.detail }}</p><div v-if="item.paths.length" class="path-list"><span v-for="path in item.paths" :key="path"><FileCode2 :size="13" />{{ path }}</span></div></div></article></div></div>

        <footer class="coverage"><div><strong>扫描范围</strong><span>已读取 {{ report.coverage.scannedFiles }} 个文本文件；已遍历目录中发现 {{ report.coverage.totalFiles }} 个文件。</span></div><p v-if="report.coverage.limited">本次为部分扫描：最多遍历 6 个子目录、读取 20 个重点文件，单文件上限 120 KB；大文件 {{ report.coverage.skippedLargeFiles }} 个，读取失败 {{ report.coverage.unreadableFiles }} 个{{ report.coverage.treeTruncated ? '，仍有目录未遍历' : '' }}。未扫描文件可能仍有风险。</p><p v-else>规则检测只提供接入前线索，不能替代实际构建、运行和人工安全审查。</p></footer>
      </template>

      <section v-else-if="!loading" class="empty-preview"><div class="empty-preview-heading"><span class="eyebrow">WHAT WE CHECK</span><span>五个核心维度</span></div><div class="preview-grid"><div><span>01</span><strong>文档与依赖</strong><p>README、依赖声明与安装说明</p></div><div><span>02</span><strong>启动方式</strong><p>入口文件与运行命令</p></div><div><span>03</span><strong>平台兼容</strong><p>Windows 专用脚本</p></div><div><span>04</span><strong>路径配置</strong><p>硬编码本机绝对路径</p></div><div><span>05</span><strong>敏感信息</strong><p>环境变量文件与疑似密钥</p></div></div></section>
    </main>
    <footer class="site-footer"><span>REPO READINESS / 01</span><span>只读检测 · GitHub 公开仓库</span></footer>
  </div>
</template>
