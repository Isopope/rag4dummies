import { ChatSession, ChatMessage, Connector, UploadedFile } from '@/types/chat';

export const mockSessions: ChatSession[] = [
  {
    id: '1',
    title: 'Analyse des ventes Q4',
    lastMessage: 'Voici le graphique des ventes...',
    timestamp: new Date(Date.now() - 1000 * 60 * 5),
    messageCount: 12,
  },
  {
    id: '2',
    title: 'Documentation API',
    lastMessage: 'Les endpoints disponibles sont...',
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2),
    messageCount: 8,
  },
  {
    id: '3',
    title: 'Résumé rapport financier',
    lastMessage: 'Le rapport indique une croissance...',
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24),
    messageCount: 5,
  },
  {
    id: '4',
    title: 'Recherche concurrentielle',
    lastMessage: 'Les principaux concurrents sont...',
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 48),
    messageCount: 15,
  },
];

export const mockMessages: ChatMessage[] = [
  {
    id: '1',
    role: 'user',
    contents: [{ type: 'text', text: 'Montre-moi les ventes du dernier trimestre avec un graphique.' }],
    timestamp: new Date(Date.now() - 1000 * 60 * 10),
  },
  {
    id: '2',
    role: 'assistant',
    contents: [
      {
        type: 'text',
        text: "Voici l'analyse des ventes du Q4 2025. Les résultats montrent une croissance significative de **23%** par rapport au trimestre précédent.",
      },
      {
        type: 'chart',
        chartData: {
          type: 'bar',
          title: 'Ventes Q4 2025 par mois',
          data: [
            { mois: 'Octobre', ventes: 45000, objectif: 40000 },
            { mois: 'Novembre', ventes: 52000, objectif: 45000 },
            { mois: 'Décembre', ventes: 68000, objectif: 55000 },
          ],
          xKey: 'mois',
          yKeys: ['ventes', 'objectif'],
        },
      },
    ],
    timestamp: new Date(Date.now() - 1000 * 60 * 9),
    sources: [
      {
        id: 'q4-report',
        title: 'Rapport commercial Q4 2025',
        excerpt: 'Ventes mensuelles, objectifs et performance consolidée du quatrième trimestre.',
      },
      {
        id: 'sales-forecast',
        title: 'Prévisions ventes 2025',
        excerpt: 'Objectifs commerciaux mensuels et hypothèses de croissance.',
      },
    ],
  },
  {
    id: '3',
    role: 'user',
    contents: [{ type: 'text', text: 'Peux-tu me montrer la tendance sur toute l\'année ?' }],
    timestamp: new Date(Date.now() - 1000 * 60 * 8),
  },
  {
    id: '4',
    role: 'assistant',
    contents: [
      {
        type: 'text',
        text: "Bien sûr ! Voici l'évolution des ventes mensuelles sur l'année 2025 :",
      },
      {
        type: 'chart',
        chartData: {
          type: 'area',
          title: 'Tendance des ventes 2025',
          data: [
            { mois: 'Jan', ventes: 32000 },
            { mois: 'Fév', ventes: 28000 },
            { mois: 'Mar', ventes: 35000 },
            { mois: 'Avr', ventes: 40000 },
            { mois: 'Mai', ventes: 38000 },
            { mois: 'Jun', ventes: 42000 },
            { mois: 'Jul', ventes: 36000 },
            { mois: 'Aoû', ventes: 30000 },
            { mois: 'Sep', ventes: 44000 },
            { mois: 'Oct', ventes: 45000 },
            { mois: 'Nov', ventes: 52000 },
            { mois: 'Déc', ventes: 68000 },
          ],
          xKey: 'mois',
          yKeys: ['ventes'],
        },
      },
      {
        type: 'json',
        jsonData: {
          total_annuel: '450 000 €',
          croissance: '+23%',
          meilleur_mois: 'Décembre',
          pire_mois: 'Février',
        },
      },
    ],
    timestamp: new Date(Date.now() - 1000 * 60 * 7),
    sources: [
      {
        id: 'annual-sales',
        title: 'Historique des ventes 2025',
        excerpt: 'Série mensuelle consolidée depuis les exports ERP.',
      },
    ],
    followUpSuggestions: [
      'Quels facteurs expliquent la croissance de décembre ?',
      'Compare ces résultats avec 2024.',
      'Génère un résumé exécutif en 5 points.',
    ],
  },
  {
    id: '5',
    role: 'user',
    contents: [{ type: 'text', text: 'Montre-moi la structure JSON de la réponse API.' }],
    timestamp: new Date(Date.now() - 1000 * 60 * 5),
  },
  {
    id: '6',
    role: 'assistant',
    contents: [
      {
        type: 'text',
        text: 'Voici la structure de la réponse API pour les données de vente :',
      },
      {
        type: 'code',
        code: `{
  "status": "success",
  "data": {
    "period": "Q4-2025",
    "sales": [
      {
        "month": "October",
        "revenue": 45000,
        "units_sold": 1250
      }
    ],
    "metadata": {
      "currency": "EUR",
      "generated_at": "2025-12-31T23:59:59Z"
    }
  }
}`,
        language: 'json',
      },
    ],
    timestamp: new Date(Date.now() - 1000 * 60 * 4),
    sources: [
      {
        id: 'api-docs',
        title: 'Documentation API ventes',
        excerpt: 'Schéma de réponse JSON et champs disponibles pour les endpoints analytics.',
      },
    ],
    followUpSuggestions: [
      'Donne-moi un exemple de requête cURL.',
      'Quels sont les codes d\'erreur possibles ?',
    ],
  },
  {
    id: '7',
    role: 'user',
    contents: [{ type: 'text', text: 'Liste les 5 meilleurs clients du trimestre sous forme de tableau.' }],
    timestamp: new Date(Date.now() - 1000 * 60 * 3),
  },
  {
    id: '8',
    role: 'assistant',
    contents: [
      {
        type: 'text',
        text: 'Voici les 5 meilleurs clients du Q4 2025 classés par chiffre d\'affaires :',
      },
      {
        type: 'table',
        tableData: {
          title: 'Top 5 clients — Q4 2025',
          columns: ['client', 'pays', 'commandes', 'revenu', 'marge'],
          rows: [
            { client: 'Acme Corp', pays: 'France', commandes: 42, revenu: 128500, marge: 0.34 },
            { client: 'Globex', pays: 'Allemagne', commandes: 38, revenu: 96200, marge: 0.28 },
            { client: 'Initech', pays: 'USA', commandes: 27, revenu: 81400, marge: 0.41 },
            { client: 'Umbrella', pays: 'Espagne', commandes: 31, revenu: 74900, marge: 0.22 },
            { client: 'Hooli', pays: 'USA', commandes: 19, revenu: 62100, marge: 0.36 },
          ],
        },
      },
    ],
    timestamp: new Date(Date.now() - 1000 * 60 * 2),
    followUpSuggestions: [
      'Quel client a la meilleure marge ?',
      'Affiche un graphique des revenus.',
    ],
  },
  {
    id: '9',
    role: 'user',
    contents: [{ type: 'text', text: 'Donne-moi le KPI principal et la tendance quotidienne sur 90 jours.' }],
    timestamp: new Date(Date.now() - 1000 * 60),
  },
  {
    id: '10',
    role: 'assistant',
    contents: [
      {
        type: 'chart',
        chartData: {
          type: 'kpi_card',
          title: 'Revenu total Q4',
          data: [{ value: 450000 }],
          xKey: 'value',
          yKeys: ['value'],
          kpi: { valueKey: 'value', label: 'Revenu total — Q4 2025', variation: 0.23, unit: '€' },
        },
      },
      {
        type: 'chart',
        chartData: {
          type: 'line',
          title: 'Revenu quotidien (90 derniers jours)',
          xKey: 'date',
          xKeyType: 'date',
          yKeys: ['ventes', 'objectif'],
          data: Array.from({ length: 90 }, (_, i) => {
            const d = new Date();
            d.setDate(d.getDate() - (89 - i));
            return {
              date: d.toISOString().slice(0, 10),
              ventes: Math.round(3000 + Math.sin(i / 6) * 800 + i * 25 + Math.random() * 400),
              objectif: 4000 + i * 20,
            };
          }),
        },
      },
    ],
    timestamp: new Date(),
    followUpSuggestions: [
      'Filtre sur les 7 derniers jours.',
      'Cache la série objectif.',
    ],
  },
];

export const mockConnectors: Connector[] = [
  {
    id: '1',
    name: 'Google Drive',
    type: 'cloud_storage',
    icon: 'HardDrive',
    status: 'connected',
    documentsCount: 1247,
    lastSync: new Date(Date.now() - 1000 * 60 * 30),
    description: 'Synchronise les documents depuis Google Drive',
  },
  {
    id: '2',
    name: 'Confluence',
    type: 'wiki',
    icon: 'BookOpen',
    status: 'syncing',
    documentsCount: 856,
    lastSync: new Date(),
    description: 'Pages et espaces Confluence',
  },
  {
    id: '3',
    name: 'Slack',
    type: 'messaging',
    icon: 'MessageSquare',
    status: 'connected',
    documentsCount: 3420,
    lastSync: new Date(Date.now() - 1000 * 60 * 60),
    description: 'Messages et fils de discussion Slack',
  },
  {
    id: '4',
    name: 'GitHub',
    type: 'code',
    icon: 'Github',
    status: 'error',
    documentsCount: 0,
    description: 'Repositories et documentation GitHub',
  },
  {
    id: '5',
    name: 'Notion',
    type: 'wiki',
    icon: 'FileText',
    status: 'disconnected',
    documentsCount: 0,
    description: 'Pages et bases de données Notion',
  },
  {
    id: '6',
    name: 'PostgreSQL',
    type: 'database',
    icon: 'Database',
    status: 'connected',
    documentsCount: 5200,
    lastSync: new Date(Date.now() - 1000 * 60 * 15),
    description: 'Tables et vues de la base de données',
  },
];

export const mockUploadedFiles: UploadedFile[] = [
  {
    id: '1',
    name: 'rapport-annuel-2025.pdf',
    size: '4.2 MB',
    type: 'application/pdf',
    status: 'indexed',
    uploadedAt: new Date(Date.now() - 1000 * 60 * 60 * 24 * 2),
  },
  {
    id: '2',
    name: 'specifications-techniques.docx',
    size: '1.8 MB',
    type: 'application/docx',
    status: 'indexed',
    uploadedAt: new Date(Date.now() - 1000 * 60 * 60 * 24),
  },
  {
    id: '3',
    name: 'données-clients-q4.csv',
    size: '12.5 MB',
    type: 'text/csv',
    status: 'processing',
    progress: 67,
    uploadedAt: new Date(Date.now() - 1000 * 60 * 30),
  },
  {
    id: '4',
    name: 'architecture-système.png',
    size: '2.1 MB',
    type: 'image/png',
    status: 'uploading',
    progress: 34,
    uploadedAt: new Date(),
  },
];
