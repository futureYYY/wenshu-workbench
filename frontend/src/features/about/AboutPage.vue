<script setup lang="ts">
import { Heart, MessageCircle } from "@lucide/vue"
import { onMounted, ref } from "vue"
import { systemApi } from "@/api/endpoints"
import Button from "@/components/base/Button.vue"
import Drawer from "@/components/base/Drawer.vue"
import Logo from "@/components/base/Logo.vue"

const version = ref("1.0.0")
const donateOpen = ref(false)
const contactOpen = ref(false)

onMounted(async () => {
  try {
    version.value = (await systemApi.info()).version
  } catch {
    // 后端暂时不可用时保留默认版本号，不影响页面本身
  }
})
</script>

<template>
  <div class="ws-about">
    <section class="ws-about__hero">
      <Logo :size="64" label="文枢" />
      <div class="ws-about__intro">
        <p class="ws-about__name">文枢 <span>WenShu</span></p>
        <p class="ws-about__tagline">把散落的文本，送到它的下一站。</p>
        <p class="ws-about__lead">
          一个在本地运行的客服文本批量处理工具：批量做意图识别和长文摘要，结果可以逐条复核、修正、导出。
        </p>
      </div>
      <span class="ws-about__version">v{{ version }}</span>
    </section>

    <section class="ws-about__section" aria-labelledby="about-name">
      <h2 id="about-name">名字的由来</h2>
      <div class="ws-about__prose">
        <p><strong>文</strong>是文本、文书；<strong>枢</strong>是门轴，引申为中枢、枢纽。</p>
        <p>
          客服每天产生大量对话、工单和回访记录，它们散落在表格、系统和聊天窗口里。文枢想做的，是这些文本的“换乘站”：从始发站上车，按不同线路分流——一条去意图识别，一条去文本摘要，最后抵达可用的结构化结果。
        </p>
        <p>
          Logo 也是这个意思：左边一段墨色线进站，右边分成蓝、绿两条线，一进多出。界面里的始发站、下一站、线网图，都是同一条思路：让一条文本的旅程看得见。
        </p>
      </div>
      <div class="ws-about__route" aria-hidden="true">
        <span class="ws-about__route-dot" />
        <span class="ws-about__route-line" />
        <span class="ws-about__route-dot is-blue" />
        <span class="ws-about__route-branch is-blue" />
        <span class="ws-about__route-dot is-green" />
        <span class="ws-about__route-branch is-green" />
      </div>
    </section>

    <section class="ws-about__section" aria-labelledby="about-problem">
      <h2 id="about-problem">能解决什么问题</h2>
      <div class="ws-about__grid">
        <article class="ws-about__card">
          <span class="ws-about__num">01</span>
          <div>
            <h3>读不完</h3>
            <p>成百上千条记录，人工逐条读，耗时、容易疲劳，晚上加班也看不完。</p>
          </div>
        </article>
        <article class="ws-about__card">
          <span class="ws-about__num">02</span>
          <div>
            <h3>判不一</h3>
            <p>同一类问题，不同人给不同标签，口径难统一，质检和统计对不上。</p>
          </div>
        </article>
        <article class="ws-about__card">
          <span class="ws-about__num">03</span>
          <div>
            <h3>摘不出</h3>
            <p>长文摘要靠人写，慢、容易漏重点，格式还不统一。</p>
          </div>
        </article>
        <article class="ws-about__card">
          <span class="ws-about__num">04</span>
          <div>
            <h3>改不动、留不下</h3>
            <p>模型结果有错时，改了没有痕迹；导出还要手工拼表，复核过程无法追溯。</p>
          </div>
        </article>
      </div>
      <p class="ws-about__solution">
        文枢把这几件事放进一个工作台：<strong>批量跑</strong>、<strong>可配置</strong>、<strong>可复核</strong>、<strong>可导出</strong>。
      </p>
    </section>

    <section class="ws-about__section" aria-labelledby="about-who">
      <h2 id="about-who">适合谁</h2>
      <div class="ws-about__chips">
        <span>客服一线</span>
        <span>质检 / 运营</span>
        <span>需要批量处理文本的个人和小团队</span>
      </div>
    </section>

    <section class="ws-about__section" aria-labelledby="about-how">
      <h2 id="about-how">怎么用</h2>
      <ol class="ws-about__steps">
        <li>
          <span class="ws-about__step-num">1</span>
          <strong>上传文件</strong>
          <span>把 csv、xlsx、txt 拖进始发站</span>
        </li>
        <li>
          <span class="ws-about__step-num">2</span>
          <strong>选文本列</strong>
          <span>点表头选择要处理的列，预览拼接结果</span>
        </li>
        <li>
          <span class="ws-about__step-num">3</span>
          <strong>设任务</strong>
          <span>选意图识别或文本摘要，配并发和条数</span>
        </li>
        <li>
          <span class="ws-about__step-num">4</span>
          <strong>运行</strong>
          <span>实时进度、结果表和线网图</span>
        </li>
        <li>
          <span class="ws-about__step-num">5</span>
          <strong>复核并导出</strong>
          <span>修正结果、标记复核，导出 xlsx / csv</span>
        </li>
      </ol>
      <p class="ws-about__note">
        支持 txt、md、csv、xlsx、xls；单文件 50 MB、单任务 10 万行；模型走 OpenAI 兼容接口，也可以先用内置演示模型体验。文本会发送到你配置的模型接口，请使用符合合规要求的模型服务。
      </p>
    </section>

    <section class="ws-about__author" aria-labelledby="about-author">
      <div class="ws-about__avatar" aria-hidden="true">齐</div>
      <div>
        <h2 id="about-author">作者</h2>
        <p class="ws-about__author-name">齐雨凡</p>
        <p class="ws-about__author-role">客服 AI 开发者 · 文枢作者</p>
        <p class="ws-about__author-text">
          做文枢的起点很简单：每天都有大量文本要读、要判、要写摘要。模型并不缺，缺的是一个一线人员敢用、用得顺、结果能复核的工具。这个工具不是想让 AI 替掉客服，而是想让客服把时间花在真正需要人的地方。
        </p>
      </div>
    </section>

    <section class="ws-about__donate" aria-labelledby="about-donate">
      <div>
        <h2 id="about-donate">赞赏支持</h2>
        <p>如果文枢帮你节省了时间，可以请我喝杯咖啡。赞赏完全自愿，不影响任何功能。</p>
      </div>
      <Button variant="secondary" @click="donateOpen = true">
        <template #icon><Heart :size="16" :stroke-width="1.75" /></template>
        赞赏支持
      </Button>
    </section>

    <section class="ws-about__contact" aria-labelledby="about-contact">
      <div>
        <h2 id="about-contact">合作与交流</h2>
        <p>定制、部署、二次开发或使用问题，欢迎加微信交流。添加时请备注“文枢 + 来意”。</p>
      </div>
      <Button variant="secondary" @click="contactOpen = true">
        <template #icon><MessageCircle :size="16" :stroke-width="1.75" /></template>
        加微信
      </Button>
    </section>

    <footer class="ws-about__footer">
      <span>文枢 v{{ version }}</span>
      <span>·</span>
      <span>© 2026 齐雨凡</span>
      <span>·</span>
      <span>不收集使用数据，文件和密钥保存在本机</span>
    </footer>

    <Drawer v-model:open="donateOpen" title="赞赏支持" :width="640">
      <div class="ws-about__qrs">
        <figure>
          <img src="/donate/alipay-qr.png" alt="支付宝收款二维码" />
          <figcaption>支付宝</figcaption>
        </figure>
        <figure>
          <img src="/donate/wechat-qr.png" alt="微信支付收款二维码" />
          <figcaption>微信支付</figcaption>
        </figure>
      </div>
      <p class="ws-about__donate-note">赞赏完全自愿，不影响任何功能。谢谢你的支持。</p>
    </Drawer>
    <Drawer v-model:open="contactOpen" title="合作与交流" :width="520">
      <div class="ws-about__contact-card">
        <img src="/contact/wechat.png" alt="作者微信二维码，合作交流" />
        <p>微信：合作 / 交流</p>
      </div>
      <p class="ws-about__donate-note">添加时请备注“文枢 + 来意”。</p>
    </Drawer>
  </div>
</template>

<style scoped>
.ws-about {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  max-width: 980px;
  padding-top: var(--space-2);
  padding-bottom: var(--space-8);
}

.ws-about__hero {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: var(--space-6);
  padding: var(--space-8);
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
}

.ws-about__hero::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3px;
  content: "";
  background: linear-gradient(90deg, var(--line-0), var(--line-1));
  opacity: 0.85;
}

.ws-about__hero > :deep(.ws-logo) {
  flex: 0 0 auto;
  margin-top: 4px;
}

.ws-about__intro {
  min-width: 0;
}

.ws-about__name {
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: 600;
  letter-spacing: 0.02em;
}

.ws-about__name span {
  margin-left: var(--space-2);
  color: var(--ink-3);
  font-size: var(--text-lg);
  font-weight: 400;
}

.ws-about__tagline {
  margin: var(--space-2) 0 0;
  font-size: var(--text-lg);
}

.ws-about__lead {
  max-width: 640px;
  margin: var(--space-2) 0 0;
  color: var(--ink-2);
  line-height: 1.8;
}

.ws-about__version {
  align-self: flex-start;
  margin-left: auto;
  padding: 2px 10px;
  color: var(--ink-3);
  font-size: var(--text-sm);
  white-space: nowrap;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
}

.ws-about__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ws-about h2 {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}

.ws-about__prose {
  display: grid;
  gap: var(--space-2);
  max-width: 800px;
  color: var(--ink-2);
  line-height: 1.9;
}

.ws-about__prose p {
  margin: 0;
}

.ws-about__prose strong {
  color: var(--ink);
  font-weight: 600;
}

.ws-about__route {
  position: relative;
  display: flex;
  align-items: center;
  width: 260px;
  height: 40px;
  margin-top: var(--space-1);
}

.ws-about__route-dot,
.ws-about__route-line,
.ws-about__route-branch {
  position: absolute;
  display: block;
}

.ws-about__route-dot {
  width: 8px;
  height: 8px;
  background: var(--ink);
  border-radius: 50%;
}

.ws-about__route-dot:first-child {
  left: 0;
}

.ws-about__route-dot.is-blue {
  left: 132px;
  background: var(--line-0);
}

.ws-about__route-dot.is-green {
  left: 132px;
  background: var(--line-1);
  transform: translateY(20px);
}

.ws-about__route-line {
  top: 19px;
  left: 8px;
  width: 124px;
  height: 2px;
  background: var(--ink);
  opacity: 0.35;
}

.ws-about__route-branch {
  left: 132px;
  width: 120px;
  height: 2px;
  border-radius: 2px;
}

.ws-about__route-branch.is-blue {
  top: 19px;
  background: var(--line-0);
  transform: rotate(-7deg);
  transform-origin: left center;
}

.ws-about__route-branch.is-green {
  top: 39px;
  background: var(--line-1);
  transform: rotate(7deg);
  transform-origin: left center;
}

.ws-about__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.ws-about__card {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
}

.ws-about__num {
  color: var(--line-0);
  font-size: var(--text-sm);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.ws-about__card h3 {
  margin: 0 0 var(--space-1);
  font-size: var(--text-base);
  font-weight: 600;
}

.ws-about__card p {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
  line-height: 1.7;
}

.ws-about__solution {
  margin: 0;
  padding: var(--space-4);
  color: var(--ink-2);
  background: var(--surface-2);
  border-radius: var(--radius-panel);
}

.ws-about__solution strong {
  color: var(--ink);
  font-weight: 600;
}

.ws-about__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ws-about__chips span {
  padding: var(--space-1) var(--space-3);
  color: var(--ink-2);
  font-size: var(--text-sm);
  background: var(--surface-2);
  border-radius: var(--radius-pill);
}

.ws-about__steps {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-3);
  padding: 0;
  margin: 0;
  list-style: none;
}

.ws-about__steps li {
  display: grid;
  gap: var(--space-1);
  align-content: start;
  padding: var(--space-3);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
}

.ws-about__step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--surface);
  font-size: var(--text-xs);
  font-weight: 600;
  background: var(--ink);
  border-radius: 50%;
}

.ws-about__steps strong {
  font-size: var(--text-sm);
  font-weight: 600;
}

.ws-about__steps li > span:last-child {
  color: var(--ink-3);
  font-size: var(--text-xs);
  line-height: 1.6;
}

.ws-about__note {
  margin: 0;
  color: var(--ink-3);
  font-size: var(--text-sm);
}

.ws-about__author {
  display: flex;
  gap: var(--space-4);
  align-items: flex-start;
  padding: var(--space-6);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
}

.ws-about__avatar {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  color: var(--surface);
  font-size: var(--text-lg);
  font-weight: 600;
  background: var(--ink);
  border-radius: 50%;
}

.ws-about__author-name {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
}

.ws-about__author-role {
  margin: var(--space-1) 0 0;
  color: var(--ink-3);
  font-size: var(--text-sm);
}

.ws-about__author-text {
  max-width: 760px;
  margin: var(--space-3) 0 0;
  color: var(--ink-2);
  line-height: 1.8;
}

.ws-about__donate,
.ws-about__contact {
  display: flex;
  gap: var(--space-4);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-6);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
}

.ws-about__donate h2,
.ws-about__contact h2 {
  margin: 0;
}

.ws-about__donate p,
.ws-about__contact p {
  margin: var(--space-2) 0 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-about__footer {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding-top: var(--space-2);
  color: var(--ink-3);
  font-size: var(--text-xs);
}

.ws-about__qrs {
  display: flex;
  gap: var(--space-6);
  justify-content: center;
}

.ws-about__qrs figure {
  flex: 1;
  max-width: 240px;
  margin: 0;
  text-align: center;
}

.ws-about__qrs img {
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: #fff;
}

.ws-about__qrs figcaption {
  margin-top: var(--space-2);
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-about__contact-card {
  display: grid;
  justify-items: center;
  gap: var(--space-2);
}

.ws-about__contact-card img {
  display: block;
  width: 260px;
  max-width: 100%;
  height: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-panel);
  background: #fff;
}

.ws-about__contact-card p {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--text-sm);
}

.ws-about__donate-note {
  margin: var(--space-4) 0 0;
  color: var(--ink-3);
  font-size: var(--text-sm);
  text-align: center;
}

@media (max-width: 900px) {
  .ws-about__hero {
    flex-wrap: wrap;
    padding: var(--space-6);
  }

  .ws-about__version {
    margin-left: 0;
  }

  .ws-about__grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .ws-about__steps {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ws-about__donate,
  .ws-about__contact {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
