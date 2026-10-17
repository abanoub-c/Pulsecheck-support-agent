import { z } from 'zod';

export const chatSchema = z.object({
  thread_id: z.string().min(8).max(100),
  customer_id: z.string().regex(/^CUST-\d{4}$/),
  message_id: z.string().min(8).max(64).optional(),
  message: z.string().trim().min(1).max(Number(process.env.MAX_MESSAGE_CHARS ?? 500)),
});

export const customerQuerySchema = z.object({
  q: z.string().max(200).optional().default(''),
  status: z.enum(['All', 'Active', 'Inactive', 'Pending']).optional().default('All'),
  category: z.enum(['All', 'billing', 'technical', 'refund', 'other']).optional().default('All'),
  sort: z.enum(['customer_id', 'company_name', 'contact_name', 'contact_email', 'status', 'assigned_category', 'signup_date', 'none']).optional().default('company_name'),
  dir: z.enum(['asc', 'desc']).optional().default('asc'),
  page: z.coerce.number().int().min(1).max(10000).optional().default(1),
  page_size: z.coerce.number().int().min(1).max(50).optional().default(10),
});

export const analyticsQuerySchema = z.object({ days: z.coerce.number().int().min(1).max(30).optional().default(30) });
export const decisionSchema = z.object({
  action: z.enum(['approve', 'edit', 'reject']),
  customer_message: z.string().max(2000).optional(),
  note: z.string().max(500).optional(),
});
