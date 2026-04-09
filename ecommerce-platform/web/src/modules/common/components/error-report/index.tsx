"use client"

import { Dialog, Transition } from "@headlessui/react"
import { Button } from "@medusajs/ui"
import React, { Fragment, useState, useRef } from "react"

import Report from "@modules/common/icons/report"
import X from "@modules/common/icons/x"
import Spinner from "@modules/common/icons/spinner"

type FormState = "idle" | "submitting" | "success" | "error"

const INGEST_API_URL = process.env.NEXT_PUBLIC_INGEST_API_URL || "http://localhost:8000"

const ErrorReportButton = () => {
  const [isOpen, setIsOpen] = useState(false)
  const [formState, setFormState] = useState<FormState>("idle")
  const [email, setEmail] = useState("")
  const [description, setDescription] = useState("")
  const [images, setImages] = useState<File[]>([])
  const [imagePreviews, setImagePreviews] = useState<string[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const resetForm = () => {
    setEmail("")
    setDescription("")
    setImages([])
    setImagePreviews([])
    setFormState("idle")
  }

  const handleClose = () => {
    setIsOpen(false)
    setTimeout(resetForm, 300)
  }

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []) as File[]
    if (files.length === 0) return
    
    // Only take the first file since backend accepts single attachment
    const file = files[0]
    setImages([file])
    
    // Clean up old preview if exists
    imagePreviews.forEach(preview => URL.revokeObjectURL(preview))
    setImagePreviews([URL.createObjectURL(file)])
  }

  const removeImage = (index: number) => {
    URL.revokeObjectURL(imagePreviews[index])
    setImages(images.filter((_: File, i: number) => i !== index))
    setImagePreviews(imagePreviews.filter((_: string, i: number) => i !== index))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!email.trim() || !description.trim()) return
    
    setFormState("submitting")
    
    try {
      const formData = new FormData()
      formData.append("text_desc", description)
      formData.append("reporter_email", email)
      // Only send the first image as file_attachment (backend accepts single file)
      if (images.length > 0) {
        formData.append("file_attachment", images[0])
      }
      
      const response = await fetch(`${INGEST_API_URL}/api/ingest`, {
        method: "POST",
        body: formData,
      })
      
      if (!response.ok) throw new Error("Failed to submit report")
      
      setFormState("success")
      setTimeout(handleClose, 2000)
    } catch {
      setFormState("error")
    }
  }

  return (
    <>
      {/* Floating Button - Expandable pill design */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 group flex items-center gap-2 h-12 px-4 bg-ui-bg-interactive text-ui-fg-on-color rounded-full shadow-lg hover:bg-ui-bg-interactive-hover transition-all duration-300 hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-ui-border-interactive focus:ring-offset-2"
        aria-label="Report an issue"
        data-testid="error-report-button"
      >
        <span className="text-sm font-medium whitespace-nowrap">Having problems?</span>
        <Report size="20" color="currentColor" />
      </button>

      {/* Modal */}
      <Transition appear show={isOpen} as={Fragment}>
        <Dialog as="div" className="relative z-[100]" onClose={handleClose}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-300"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-200"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-lg transform overflow-hidden rounded-lg bg-white shadow-xl transition-all">
                  {/* Header */}
                  <div className="flex items-center justify-between border-b border-ui-border-base px-6 py-4">
                    <Dialog.Title className="text-lg font-semibold text-ui-fg-base">
                      Report an Issue
                    </Dialog.Title>
                    <button
                      onClick={handleClose}
                      className="text-ui-fg-subtle hover:text-ui-fg-base transition-colors"
                      aria-label="Close"
                    >
                      <X size={20} />
                    </button>
                  </div>

                  {/* Content */}
                  <div className="px-6 py-4">
                    {formState === "success" ? (
                      <div className="text-center py-8">
                        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-green-100 flex items-center justify-center">
                          <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        </div>
                        <h3 className="text-lg font-medium text-ui-fg-base mb-2">Thank you!</h3>
                        <p className="text-ui-fg-subtle">Your report has been sent. We'll look into it right away.</p>
                      </div>
                    ) : (
                      <>
                        {/* Friendly intro */}
                        <div className="mb-6 p-4 bg-ui-bg-subtle rounded-lg">
                          <p className="text-sm text-ui-fg-subtle">
                            <span className="font-medium text-ui-fg-base">Hi there! 👋</span>
                            <br />
                            Something not working as expected? We're here to help. Tell us what happened and we'll get it sorted out for you.
                          </p>
                        </div>

                        <form onSubmit={handleSubmit} className="space-y-4">
                          {/* Email */}
                          <div>
                            <label htmlFor="report-email" className="block text-sm font-medium text-ui-fg-base mb-1">
                              Your email <span className="text-rose-500">*</span>
                            </label>
                            <input
                              id="report-email"
                              type="email"
                              value={email}
                              onChange={(e) => setEmail(e.target.value)}
                              placeholder="e.g., your@email.com"
                              className="w-full px-4 py-2.5 border border-ui-border-base rounded-md bg-ui-bg-field focus:outline-none focus:ring-2 focus:ring-ui-border-interactive text-sm"
                              required
                              disabled={formState === "submitting"}
                            />
                            <p className="mt-1 text-xs text-ui-fg-muted">We'll use this to follow up on your report</p>
                          </div>

                          {/* Description */}
                          <div>
                            <label htmlFor="report-description" className="block text-sm font-medium text-ui-fg-base mb-1">
                              Tell us more <span className="text-rose-500">*</span>
                            </label>
                            <textarea
                              id="report-description"
                              value={description}
                              onChange={(e) => setDescription(e.target.value)}
                              placeholder="What were you trying to do? What happened instead? Any error messages you saw?"
                              rows={4}
                              className="w-full px-4 py-2.5 border border-ui-border-base rounded-md bg-ui-bg-field focus:outline-none focus:ring-2 focus:ring-ui-border-interactive text-sm resize-none"
                              required
                              disabled={formState === "submitting"}
                            />
                            <p className="mt-1 text-xs text-ui-fg-muted">The more details you share, the faster we can help</p>
                          </div>

                          {/* Image upload */}
                          <div>
                            <label className="block text-sm font-medium text-ui-fg-base mb-1">
                              Screenshot (optional)
                            </label>
                            <p className="text-xs text-ui-fg-muted mb-2">A picture is worth a thousand words! Add a screenshot.</p>
                            
                            <input
                              ref={fileInputRef}
                              type="file"
                              accept="image/*"
                              onChange={handleImageChange}
                              className="hidden"
                              disabled={formState === "submitting" || images.length >= 1}
                            />
                            
                            {imagePreviews.length > 0 && (
                              <div className="flex flex-wrap gap-2 mb-2">
                                {imagePreviews.map((preview: string, index: number) => (
                                  <div key={index} className="relative group">
                                    <img
                                      src={preview}
                                      alt={`Preview ${index + 1}`}
                                      className="w-16 h-16 object-cover rounded-md border border-ui-border-base"
                                    />
                                    <button
                                      type="button"
                                      onClick={() => removeImage(index)}
                                      className="absolute -top-2 -right-2 w-5 h-5 bg-rose-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                      aria-label={`Remove image ${index + 1}`}
                                    >
                                      <X size={12} />
                                    </button>
                                  </div>
                                ))}
                              </div>
                            )}
                            
                            {images.length < 1 && (
                              <button
                                type="button"
                                onClick={() => fileInputRef.current?.click()}
                                className="w-full py-3 border-2 border-dashed border-ui-border-base rounded-md text-sm text-ui-fg-subtle hover:border-ui-border-interactive hover:text-ui-fg-base transition-colors"
                                disabled={formState === "submitting"}
                              >
                                + Add screenshot
                              </button>
                            )}
                          </div>

                          {/* Error message */}
                          {formState === "error" && (
                            <div className="p-3 bg-rose-50 border border-rose-200 rounded-md">
                              <p className="text-sm text-rose-700">
                                Oops! Something went wrong while sending your report. Please try again.
                              </p>
                            </div>
                          )}

                          {/* Submit button */}
                          <div className="pt-2">
                            <Button
                              type="submit"
                              className="w-full"
                              disabled={formState === "submitting" || !email.trim() || !description.trim()}
                            >
                              {formState === "submitting" ? (
                                <span className="flex items-center justify-center gap-2">
                                  <Spinner />
                                  Sending...
                                </span>
                              ) : (
                                "Send Report"
                              )}
                            </Button>
                          </div>
                        </form>
                      </>
                    )}
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>
    </>
  )
}

export default ErrorReportButton
