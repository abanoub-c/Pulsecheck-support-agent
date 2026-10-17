import { expect, test } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

test('chat refund handoff is visible in Ops, a human decision resumes the transcript, and analytics controls work', async ({ page, request }) => {
  await request.post('/api/demo/reset');
  const invalidCustomer = await request.post('/api/chat', { data: { thread_id: 'invalid-demo-thread', customer_id: 'CUST-9999', message: 'hello' } });
  expect(invalidCustomer.status()).toBe(403);
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto('/chat');
  await expect(page.getByRole('heading', { name: 'Chat' })).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/\b(Manus|Bolt)\b/i);
  await expect(page.getByRole('button', { name: 'Light' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Dark' }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: /refund for last month.s Business plan charge/i }).click();
  await expect(page.getByText(/I prepared a \$299 refund request for manager review/i)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/Passed to a human specialist/i)).toBeVisible();
  const traceToggle = page.getByRole('button', { name: /Thought for/ }).last();
  await traceToggle.click();
  await expect(page.getByRole('heading', { name: 'Steps' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Tool calls' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'State' })).toBeVisible();
  await page.reload();
  await expect(page.getByText(/I prepared a \$299 refund request for manager review/i)).toBeVisible();
  await page.getByRole('button', { name: /Thought for/ }).last().click();
  await expect(page.getByRole('heading', { name: 'Tool calls' })).toBeVisible();

  await page.getByRole('link', { name: 'Dashboard' }).click();
  const newRefundRow = page.locator('.queue-table tbody tr').filter({ hasText: 'Halcyon Cloud' }).first();
  await expect(newRefundRow).toBeVisible();
  await newRefundRow.click();
  await expect(page.locator('#customer-message')).toHaveValue(/299/);
  await page.getByRole('button', { name: 'Approve' }).click();
  await expect(page.getByText(/Decision sent\. The conversation has been updated/i)).toBeVisible();

  await page.getByRole('link', { name: 'Chat' }).click();
  await expect(page.getByText(/I.ve approved your \$299 refund request/i)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/Human specialist/)).toBeVisible();

  await page.getByRole('link', { name: 'Analytics' }).click();
  await expect(page.getByRole('heading', { name: 'Category Breakdown' })).toBeVisible();
  await page.getByRole('button', { name: 'Last 7 days' }).click();
  await expect(page.getByRole('button', { name: 'Last 7 days' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'View as table' }).first().click();
  await expect(page.getByRole('table')).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test('Clients search, URL query state, sort cycle, filters, and pagination work', async ({ page }) => {
  await page.goto('/clients');
  const search = page.getByLabel('Search clients');
  await search.fill('Crestpoint');
  await expect(page.getByRole('row', { name: /Crestpoint Systems/ })).toBeVisible();
  await expect(page).toHaveURL(/q=Crestpoint/);

  const nameHeader = page.getByRole('columnheader', { name: /Name/ });
  await nameHeader.getByRole('button').click();
  await expect(nameHeader).toHaveAttribute('aria-sort', 'descending');
  await expect(page).toHaveURL(/sort=company_name&dir=desc/);
  await nameHeader.getByRole('button').click();
  await expect(nameHeader).toHaveAttribute('aria-sort', 'none');
  await expect(page).toHaveURL(/sort=none/);
  await nameHeader.getByRole('button').click();
  await expect(nameHeader).toHaveAttribute('aria-sort', 'ascending');
  await expect(page).toHaveURL(/sort=company_name&dir=asc/);

  await page.getByRole('button', { name: /Clear filters/ }).click();
  await expect(page.locator('.clients-table tbody tr')).toHaveCount(10);
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.locator('.clients-table tbody tr')).toHaveCount(10);
  await page.getByLabel('Rows').selectOption('25');
  await expect(page.locator('.clients-table tbody tr')).toHaveCount(25);
  await expect(page.getByText('Page 1 of 1')).toBeVisible();
  await page.getByLabel('Status').selectOption('Pending');
  await expect(page).toHaveURL(/status=Pending/);
  await expect(page.locator('.clients-table tbody tr')).toHaveCount(6);
  await page.getByLabel('Category').selectOption('refund');
  await expect(page).toHaveURL(/category=refund/);
  await page.getByRole('button', { name: /Clear filters/ }).click();
  await search.fill('CUST-0001');
  const clientRow = page.getByRole('row', { name: /CUST-0001/ });
  await expect(clientRow).toBeVisible();
  await expect(clientRow.getByRole('button', { name: /Chat with/ })).toBeDisabled();
  const viewButton = clientRow.getByRole('button', { name: 'View' });
  await viewButton.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(viewButton).toBeFocused();
});

test('layout stays within 360, 900, and 1440 pixels; mobile navigation traps and restores focus', async ({ page }) => {
  const screens = [
    { path: '/dashboard', title: 'Dashboard', ready: '.queue-table' },
    { path: '/clients', title: 'Clients', ready: '.clients-table' },
    { path: '/chat', title: 'Chat', ready: '.chat-empty' },
    { path: '/analytics', title: 'Analytics', ready: '.chart-card' },
  ];
  for (const width of [360, 900, 1440]) {
    await page.setViewportSize({ width, height: width === 360 ? 800 : 900 });
    for (const screen of screens) {
      await page.goto(screen.path);
      await expect(page.getByRole('heading', { name: screen.title })).toBeVisible();
      await expect(page.locator(screen.ready).first()).toBeVisible({ timeout: 10_000 });
      if (screen.path === '/analytics') {
        await expect.poll(() => page.locator('.donut-wrap .recharts-sector').evaluateAll((paths) => paths.length === 4 && paths.every((path) => (path.getAttribute('d')?.length ?? 0) > 100))).toBe(true);
        await expect.poll(() => page.locator('.bar-chart-wrap .recharts-rectangle').evaluateAll((paths) => paths.length >= 8 && Math.max(...paths.map((path) => (path as SVGGraphicsElement).getBBox().height)) > 100)).toBe(true);
      }
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      if (width === 360 || screen.path === '/dashboard') await page.screenshot({ path: `/tmp/pulsecheck-${width}-${screen.title.toLowerCase()}.png`, fullPage: true, animations: 'disabled' });
    }
  }

  await page.setViewportSize({ width: 360, height: 800 });
  const menu = page.getByRole('button', { name: 'Open navigation' });
  await menu.focus();
  await menu.click();
  await expect(page.locator('.app-sidebar')).toHaveAttribute('aria-modal', 'true');
  await expect(page.locator('.app-sidebar .mobile-close')).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect.poll(() => page.evaluate(() => Boolean(document.querySelector('.app-sidebar')?.contains(document.activeElement)))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(page.locator('.app-sidebar')).not.toHaveClass(/is-mobile-open/);
  await expect(menu).toBeFocused();
});

test('collapsed desktop sidebar hides section captions and labels', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/clients');
  const sidebar = page.locator('.app-sidebar');
  await page.getByRole('button', { name: 'Collapse sidebar' }).click();
  await expect(sidebar).toHaveClass(/is-collapsed/);
  await expect(sidebar.locator('.nav-caption')).toHaveCount(2);
  await expect(sidebar.locator('.nav-caption').first()).toBeHidden();
  await expect(sidebar.locator('.nav-caption').nth(1)).toBeHidden();
  await expect(sidebar.locator('.nav-label')).toHaveCount(0);
  const expand = page.getByRole('button', { name: 'Expand sidebar' });
  await expect(expand).toBeVisible();
  const brandBox = await sidebar.locator('.brand-mark').boundingBox();
  const expandBox = await expand.boundingBox();
  const sidebarBox = await sidebar.boundingBox();
  if (!brandBox || !expandBox || !sidebarBox) throw new Error('Collapsed sidebar geometry is unavailable.');
  expect(expandBox.y).toBeGreaterThanOrEqual(brandBox.y + brandBox.height);
  expect(expandBox.x).toBeGreaterThanOrEqual(sidebarBox.x);
  expect(expandBox.x + expandBox.width).toBeLessThanOrEqual(sidebarBox.x + sidebarBox.width);
  await page.screenshot({ path: '/tmp/pulsecheck-collapsed-sidebar.png', animations: 'disabled' });
});

test('mobile drawer expands labels even when the saved desktop rail is collapsed', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.addInitScript(() => localStorage.setItem('pulsecheck-sidebar-collapsed', 'true'));
  await page.goto('/clients');
  const sidebar = page.locator('.app-sidebar');
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await expect(sidebar).toHaveClass(/is-mobile-open/);
  await expect(sidebar).not.toHaveClass(/is-collapsed/);
  await expect(sidebar.locator('.nav-label')).toHaveCount(4);
  await expect(sidebar.locator('.nav-caption').first()).toBeVisible();
  await expect(sidebar.locator('.settings-caption')).toBeVisible();
});

test('non-chat routes keep slim themed scrollbars without native arrow buttons', async ({ page }) => {
  await page.setViewportSize({ width: 1154, height: 611 });
  await page.goto('/clients');
  const scrollbar = await page.evaluate(() => {
    const root = document.documentElement;
    return {
      width: getComputedStyle(root).scrollbarWidth,
      color: getComputedStyle(root).scrollbarColor,
      webkitWidth: getComputedStyle(root, '::-webkit-scrollbar').width,
      buttonDisplay: getComputedStyle(root, '::-webkit-scrollbar-button').display,
      thumbRadius: getComputedStyle(root, '::-webkit-scrollbar-thumb').borderTopLeftRadius,
    };
  });
  expect(scrollbar.width).toBe('thin');
  expect(scrollbar.color).toContain('rgba(0, 0, 0, 0)');
  expect(scrollbar.webkitWidth).toBe('9px');
  expect(scrollbar.buttonDisplay).toBe('none');
  expect(scrollbar.thumbRadius).toBe('999px');
  await page.screenshot({ path: '/tmp/pulsecheck-themed-scrollbar.png', animations: 'disabled' });
});

test('Chat hides scrollbar visuals while preserving scroll behavior', async ({ page }) => {
  await page.setViewportSize({ width: 1154, height: 611 });
  await page.goto('/chat');
  const transcript = page.locator('.transcript');
  await expect(transcript).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.classList.contains('chat-route'))).toBe(true);
  const styles = await page.evaluate(() => {
    const root = document.documentElement;
    const transcript = document.querySelector('.transcript') as HTMLElement;
    return {
      rootScrollbarWidth: getComputedStyle(root).scrollbarWidth,
      rootScrollbarDisplay: getComputedStyle(root, '::-webkit-scrollbar').display,
      transcriptScrollbarWidth: getComputedStyle(transcript).scrollbarWidth,
      transcriptScrollbarDisplay: getComputedStyle(transcript, '::-webkit-scrollbar').display,
      transcriptOverflowY: getComputedStyle(transcript).overflowY,
    };
  });
  expect(styles.rootScrollbarWidth).toBe('none');
  expect(styles.rootScrollbarDisplay).toBe('none');
  expect(styles.transcriptScrollbarWidth).toBe('none');
  expect(styles.transcriptScrollbarDisplay).toBe('none');
  expect(styles.transcriptOverflowY).toBe('auto');
  await transcript.evaluate((element) => {
    const el = element as HTMLElement;
    el.style.height = '180px';
    el.style.minHeight = '0px';
    el.style.maxHeight = '180px';
    el.style.scrollBehavior = 'auto';
    el.scrollTop = 0;
  });
  await transcript.hover();
  await page.mouse.wheel(0, 300);
  await expect.poll(() => transcript.evaluate((element) => (element as HTMLElement).scrollTop)).toBeGreaterThan(0);
  const scrollState = await transcript.evaluate((element) => ({
    top: (element as HTMLElement).scrollTop,
    clientHeight: (element as HTMLElement).clientHeight,
    scrollHeight: (element as HTMLElement).scrollHeight,
  }));
  expect(scrollState.scrollHeight).toBeGreaterThan(scrollState.clientHeight);
  expect(scrollState.top).toBeGreaterThan(0);
  await page.goto('/clients');
  await expect.poll(() => page.evaluate(() => document.documentElement.classList.contains('chat-route'))).toBe(false);
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).scrollbarWidth)).toBe('thin');
});
