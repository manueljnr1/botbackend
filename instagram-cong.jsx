









'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import useSWR from 'swr'

import { fetcherWithAuth } from '@/src/app/api/fetcher'
import { Button } from '@/src/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/src/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/src/components/ui/dialog'
import { Input } from '@/src/components/ui/input'
import { Label } from '@/src/components/ui/label'
import api from '@/src/lib/api'
import Cookies from 'js-cookie'
import { Instagram, Loader2 } from 'lucide-react' // Import Loader2
import { Switch } from './ui/switch'

export default function InstagramConfiguration() {
  const token = Cookies.get('access_token')
  const apiKey = Cookies.get('tenant_api_key')

  // --- REMOVED: `open` and `formData` states are no longer needed ---
  // const [open, setOpen] = useState(false)
  // const [formData, setFormData] = useState(...)

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsData, setSettingsData] = useState({
    bot_enabled: false,
    auto_reply_enabled: false,
    webhook_verify_token: '',
  })

  const {
    data: instagramConfig,
    error,
    isLoading,
    mutate,
  } = useSWR(
    token && apiKey
      ? [
          `${process.env.NEXT_PUBLIC_BASE_URL}/api/instagram/status`,
          {
            headers: {
              Authorization: `Bearer ${token}`,
              'X-API-Key': apiKey,
            },
          },
        ]
      : null,
    fetcherWithAuth
  )

  // --- REMOVED: `handleFormChange` is no longer needed ---

  // --- REMOVED: `handleInstagramSetup` is no longer needed ---

  /**
   * The function `handleDeleteIntegration` deletes an Instagram integration using an API call and
   * displays success or error messages accordingly.
   */
  const handleDeleteIntegration = async () => {
    try {
      const res = await api.delete('/api/instagram/integration', {
        requireAuth: true,
        useApiKey: true,
      })

      toast.success(res.message || 'Instagram integration deleted successfully')
      mutate() // Re-fetch status, which will now be a 404
    } catch (error) {
      toast.error(error?.message || 'Failed to delete integration')
      console.error('Delete integration error:', error)
    }
  }

  const handleUpdateSettings = async () => {
    try {
      const res = await api.put('/api/instagram/settings', settingsData, {
        requireAuth: true,
        useApiKey: true,
      })
      toast.success(res.message || 'Settings updated successfully')
      setSettingsOpen(false)
      mutate() // Re-fetch status
    } catch (err) {
      toast.error(err?.message || 'Failed to update settings')
    }
  }

  // --- NEW: Simplified function to render the main action button ---
  const renderPrimaryButton = () => {
    if (isLoading) {
      return (
        <Button variant='secondary' className='h-12 w-48' disabled>
          <Loader2 className='mr-2 h-4 w-4 animate-spin' />
          Loading...
        </Button>
      )
    }

    // If API returns 404, it means no integration exists. Show "Connect" button.
    if (error && error.status === 404) {
      return (
        // This is now an <a> tag linking directly to the backend auth endpoint
        <a
          href={`${process.env.NEXT_PUBLIC_BASE_URL}/api/instagram/auth/login`}
          // We pass the api_key via headers, so the <a> tag needs to be
          // wrapped in a component that can add headers, or use api.get
          // For simplicity, we assume /auth/login uses the API key from the cookie.
          // IF IT DOES NOT, you must use the query param:
          // href={`${process.env.NEXT_PUBLIC_BASE_URL}/api/instagram/auth/login?api_key=${apiKey}`}
        >
          <Button variant='default' className='h-12'>
            Connect with Instagram
          </Button>
        </a>
      )
    }

    // If integration exists (even in error), show "Update Settings"
    if (instagramConfig) {
      return (
        <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
          <DialogTrigger asChild>
            <Button variant='secondary' className='h-12'>
              Update Bot Settings
            </Button>
          </DialogTrigger>
          <DialogContent className='bg-gray-900 text-white border border-gray-700 gap-8'>
            <DialogHeader>
              <DialogTitle>Instagram Bot Settings</DialogTitle>
            </DialogHeader>

            <div className='space-y-5'>
              <div className='space-y-3'>
                <Label>Webhook Verify Token</Label>
                <Input
                  value={settingsData.webhook_verify_token}
                  onChange={(e) =>
                    setSettingsData({
                      ...settingsData,
                      webhook_verify_token: e.target.value,
                    })
                  }
                  placeholder='Enter webhook verify token'
                />
              </div>

              <div className='flex items-center justify-between'>
                <Label>Bot Enabled</Label>
                <Switch
                  checked={settingsData.bot_enabled}
                  onCheckedChange={(checked) =>
                    setSettingsData((prev) => ({
                      ...prev,
                      bot_enabled: checked,
                    }))
                  }
                />
              </div>

              <div className='flex items-center justify-between'>
                <Label>Auto Reply Enabled</Label>
                <Switch
                  checked={settingsData.auto_reply_enabled}
                  onCheckedChange={(checked) =>
                    setSettingsData((prev) => ({
                      ...prev,
                      auto_reply_enabled: checked,
                    }))
                  }
                />
              </div>
            </div>

            <DialogFooter className=''>
              <Button onClick={handleUpdateSettings}>Save Settings</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )
    }

    // Fallback for non-404 errors
    return (
      <Button variant='destructive' className='h-12' disabled>
        Error loading status
      </Button>
    )
  }

  // Check if integration exists and is active
  const isConnected = instagramConfig?.bot_status === 'active'

  return (
    <main className='flex flex-col gap-5'>
      <section className='flex justify-end gap-5 py-2'>
        <Dialog>
          <DialogTrigger asChild>
            <Button
              variant='destructive'
              className='h-12'
              // Disable delete button if no integration exists
              disabled={!instagramConfig}
            >
              Delete Integration
            </Button>
          </DialogTrigger>
          <DialogContent className='bg-gray-900 text-white border border-gray-700 gap-5'>
            <DialogHeader>
              <DialogTitle>Confirm Deletion</DialogTitle>
            </DialogHeader>
            <p className='text-sm text-gray-300'>
              Are you sure you want to delete the Instagram integration? This
              action cannot be undone.
            </p>
            <DialogFooter className='gap-5'>
              <Button variant='outline'>Cancel</Button>
              <Button variant='destructive' onClick={handleDeleteIntegration}>
                Confirm Delete
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* --- REMOVED: The main "Configure" dialog is gone --- */}
      </section>

      <Card className='bg-gray-900/70 border-gray-800 text-white shadow-sm'>
        <CardHeader className='flex flex-col lg:flex-row lg:justify-between gap-4'>
          <div className='flex flex-col gap-3'>
            <CardTitle className='text-xl flex items-center gap-2'>
              <Instagram className='h-5 w-5 text-pink-400' />
              Instagram Configuration
            </CardTitle>
            <CardDescription className='text-gray-400'>
              {/* MODIFIED: Updated description */}
              {isConnected
                ? `Connected as @${instagramConfig.instagram_username}`
                : 'Connect your Instagram Business account to get started.'}
            </CardDescription>
          </div>

          {/* --- MODIFIED: This now renders the correct button --- */}
          {renderPrimaryButton()}
        </CardHeader>
        <CardContent className='space-y-6'>
          <div className='grid grid-cols-1 lg:grid-cols-2 gap-6 pt-4'>
            <div className='p-4 rounded-lg bg-gray-800/30 border border-gray-700/50 space-y-3'>
              <Label className='text-white font-medium'>Connection Info</Label>
              <ul className='text-sm text-gray-300 mt-1 space-y-1'>
                <li>
                  <span className='text-gray-400'>Bot Status:</span>{' '}
                  {instagramConfig?.bot_status ?? 'Not Configured'}
                </li>
                <li>
                  <span className='text-gray-400'>Connected:</span>{' '}
                  {isConnected ? 'Yes' : 'No'}
                </li>
                <li>
                  <span className='text-gray-400'>Username:</span>{' '}
                  {instagramConfig?.instagram_username ?? 'N/A'}
                </li>
                <li>
                  <span className='text-gray-400'>Last Error:</span>{' '}
                  {instagramConfig?.last_error ?? 'None'}
                </li>
              </ul>
            </div>

            <div className='p-4 rounded-lg bg-gray-800/30 border border-gray-700/50 space-y-3'>
              <Label className='text-white font-medium'>
                Metrics & Features
              </Label>
              <ul className='text-sm text-gray-300 mt-1 space-y-1'>
                <li>
                  <span className='text-gray-400'>Bot Enabled:</span>{' '}
                  {instagramConfig?.bot_enabled ? 'Yes' : 'No'}
                </li>
                <li>
                  <span className='text-gray-400'>Webhook Subscribed:</span>{' '}
                  {instagramConfig?.webhook_subscribed ? 'Yes' : 'No'}
                </li>
                <li>
                  <span className='text-gray-400'>Error Count:</span>{' '}
                  {instagramConfig?.error_count ?? 0}
                </li>
                <li>
                  <span className='text-gray-400'>Last Message:</span>{' '}
                  {instagramConfig?.last_message_at
                    ? new Date(instagramConfig.last_message_at).toLocaleString()
                    : 'N/A'}
                </li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </main>
  )
}