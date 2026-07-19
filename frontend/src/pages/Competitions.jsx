import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { createCompetition, deleteCompetition, listCompetitions } from '../api/competitions.js'
import { listPaperAccounts } from '../api/paper.js'

export default function Competitions() {
  const queryClient = useQueryClient()
  const competitions = useQuery({ queryKey: ['competitions'], queryFn: listCompetitions })
  const accounts = useQuery({ queryKey: ['paper-accounts'], queryFn: listPaperAccounts })

  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selected, setSelected] = useState([])
  const [submitError, setSubmitError] = useState(null)

  const create = useMutation({
    mutationFn: createCompetition,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['competitions'] })
      setShowForm(false)
      setName('')
      setDescription('')
      setSelected([])
    },
    onError: (err) =>
      setSubmitError(err.response?.data?.detail ?? err.message ?? 'Request failed'),
  })
  const remove = useMutation({
    mutationFn: deleteCompetition,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['competitions'] }),
  })

  const toggle = (id) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Strategy Competitions</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="rounded bg-emerald-500 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-emerald-400"
        >
          {showForm ? 'Cancel' : 'New competition'}
        </button>
      </div>

      <p className="text-xs text-slate-500">
        Compare paper accounts over their common trading window. Rankings are risk-adjusted
        (Sharpe, then drawdown) — never total return alone. Fairness checks flag any
        difference in start date, capital, universe, costs, or benchmark.
      </p>

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            setSubmitError(null)
            create.mutate({
              name: name.trim() || `Competition ${new Date().toISOString().slice(0, 10)}`,
              description: description.trim() || null,
              account_ids: selected,
            })
          }}
          className="space-y-4 rounded-lg border border-slate-800 bg-slate-900 p-4"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1">
              <span className="block text-xs text-slate-400">Name</span>
              <input
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Sizing shoot-out"
              />
            </label>
            <label className="space-y-1">
              <span className="block text-xs text-slate-400">Description (optional)</span>
              <input
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
          </div>
          <div>
            <span className="block text-xs text-slate-400">Accounts (pick 2+)</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {(accounts.data?.items ?? []).map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => toggle(a.id)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    selected.includes(a.id)
                      ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300'
                      : 'border-slate-700 text-slate-400 hover:border-slate-500'
                  }`}
                >
                  {a.name}
                </button>
              ))}
              {accounts.data?.items?.length === 0 && (
                <span className="text-sm text-slate-500">
                  No paper accounts yet — <Link to="/paper-accounts/new" className="text-emerald-400">create some first</Link>.
                </span>
              )}
            </div>
          </div>
          {submitError && (
            <p className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {typeof submitError === 'string' ? submitError : JSON.stringify(submitError)}
            </p>
          )}
          <button
            type="submit"
            disabled={create.isPending || selected.length < 2}
            className="rounded bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
          >
            {create.isPending ? 'Creating…' : `Create with ${selected.length} account${selected.length === 1 ? '' : 's'}`}
          </button>
        </form>
      )}

      {competitions.isPending && <p className="text-sm text-slate-400">Loading competitions…</p>}
      {competitions.data?.items?.length === 0 && !showForm && (
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-8 text-center">
          <p className="text-slate-400">No competitions yet.</p>
          <p className="mt-1 text-sm text-slate-500">
            Create paper accounts with different parameters, then pit them against each other.
          </p>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {(competitions.data?.items ?? []).map((c) => (
          <div key={c.id} className="rounded-lg border border-slate-800 bg-slate-900 p-4 hover:border-slate-700">
            <div className="flex items-start justify-between">
              <Link to={`/competitions/${c.id}`} className="font-medium text-slate-100 hover:text-emerald-400">
                {c.name}
              </Link>
              <button
                onClick={() => {
                  if (window.confirm(`Delete competition "${c.name}"? (Accounts are kept.)`)) {
                    remove.mutate(c.id)
                  }
                }}
                className="text-xs text-slate-500 hover:text-red-400"
              >
                Delete
              </button>
            </div>
            {c.description && <p className="mt-1 text-sm text-slate-400">{c.description}</p>}
            <p className="mt-2 text-xs text-slate-500">
              {c.account_count} account{c.account_count === 1 ? '' : 's'} · created{' '}
              {new Date(c.created_at).toLocaleDateString()}
            </p>
            <Link
              to={`/competitions/${c.id}`}
              className="mt-3 inline-block rounded border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:border-emerald-500 hover:text-emerald-300"
            >
              View leaderboard →
            </Link>
          </div>
        ))}
      </div>
    </div>
  )
}
